import lyapunov

class Motor(object):
	def __init__(self, state0):
		self.time = 0.0
		self.state = state0
		self.Rs = 10 	#stator winding resistance - ohms
		self.Ls = 0.14 	#stator winding inductance - henrys
		self.Rr = 10 	#rotor winding resistance - ohms
		self.Lr = 0.06 	#rotor winding inductance - henrys
		self.Vr = 100.4	#rotor voltage - volts
		self.B = 0.01 	#viscous friction - N.m.s/rad
		self.K = 0.714 	#back-emf / torque constant - V.s/rad
		self.J = 0.25 	#rotational inertia - kg.m2
		self.alpha = Rs / Ls
		self.beta = Rr / Lr
		self.gamma = Vr / Lr
		self.a = K * Ls / Lr
		self.b = B / J
		self.c = K * Ls / J

	@lyapunov.State
	def state(self)
		return self._state

	@state.setter
	def state(self, x):
		self._state = x
		self._output = self.h_complete(x)

	@lyapunov.Input
	def u(self):
		pass
	
	@lyapunov.Input
	def d(self):
		""" Disturbance force at a particular time step.
			Must be function with respect to time. """
		return 0.0

	@lyapunov.Output
	def output(self):
		return self._output
	
	def __call__(self, control_effort, disturbance):
		return self.f(self._state, self.u, self.d)

	def f(self, x, u, d):
		x1, x2, x3, __ = x
		x1dot = -self.alpha*x1 + u/self.Ls
		x2dot = -self.beta*x2 + self.gamma - self.a*x1*x3
		x3dot = -self.b*x3 + self.c*x1*x2 + d/self.J
		x4dot = x3
		return [x1dot, x2dot, x3dot, x4dot]

	def h_complete(self, x):
		x1, x2, x3, x4 = x
		y = x4
		ydot = x3
		y2dot = -self.b*x3 + self.c*x1*x2
		return y, ydot, y2dot


class Observer(object):
	def __init__(self, plant):
		self.state = [0.0, 0.0, 0.0, 0.0]
		self.plant = plant
		self.Lmax = 100.0 #this value is arbitrary

	@lyapunov.State
	def state(self):
		return self._state

	@state.setter
	def state(self, xhat):
		self._state = xhat
		x1, x2, x3, x4 = xhat
		#computing observer gains...
		p = self.plant
		L4 = 25 - p.b - p.beta - p.alpha
		L3 = p.alpha*L4 + p.a*p.b*p.c*p.beta*x1**2 - 234
		L1 = ((1526 - (L3 + (p.b + p.beta)*L4 + (L4 
			+ (p.alpha - 1))*p.alpha*p.beta*p.a*p.b*p.c*x1**2)*p.alpha**2) 
			/ (p.c*(p.a*x1*x3 + x2*(p.alpha+p.beta))))
		L2 = ((-(p.alpha + p.beta)*L3 + p.alpha*L4*(p.b + p.beta) 
			+ (L4 + p.alpha)*p.beta*p.a*p.b*p.c*x1**2 - p.c*x2*L1 - 997) 
			/ (p.c*x1))
		#Set maximum gains! Otherwise they'll blow up when your estimated
		#system loses observability.
		L1 = L1 if L1 < self.Lmax else self.Lmax
		L2 = L2 if L2 < self.Lmax else self.Lmax
		self._gains = (L1, L2, L3, L4)
		#computing estimated output...
		self._output = self.plant.h_complete(xhat)

	@lyapunov.Output
	def output(self):
		return self._output

	@lyapunov.Input
	def y(self):
		pass

	@lyapunov.Input
	def u(self):
		pass

	def __call__(self):
		xdot = self.plant.f(self._state, self.u, 0.0)
		output_error = self.y[0] - self._state[3] 
		return [xidot + output_error*L 
				for (xidot, L) in zip(xdot, self._gains)]


class FBLController(object):
	"""feedback linearizing control"""
	def __init__(self, plant):
		self.plant = plant
		self._gains = (1.95, 4.69, 3.75) #(k1, k2, k3)

	@lyapunov.Input
	def x(self):
		pass

	@lyapunov.Input
	def r(self):
		pass

	@lyapunov.Input
	def y(self):
		pass

	def __call__(self):
		"""takes reference(+derivatives) & states, returns control effort"""
		#Compute the equivalent torque that makes the system linear.
		p = self.plant 
		x1, x2, x3, __ = self.x
		r, rdot, r2dot, r3dot = self.r
		u_eq = p.Ls * (r3dot + (p.alpha + p.beta)*p.c*x1*x2 - p.gamma*p.c*x1 
				+ p.a*p.c*x3*x1**2 - x3*p.b**2 - p.b*p.c*x1*x2) / (p.c*x2)
		#Now compute the control torque.
		k1, k2, k3 = self._gains
		y, ydot, y2dot = self.y
		u_c = p.Ls * (k1*(r-y) + k2*(rdot-ydot) + k3*(r2dot-y2dot)) / (p.c * x2)
		return u_eq + u_c


class SMController(object):
	"""sliding mode control"""
	def __init__(self, plant, eta_value):
		System.__init__(self, plant.state)
		self.eta = eta_value

	@lyapunov.Input
	def x(self):
		pass

	@lyapunov.Input
	def r(self):
		pass

	@lyapunov.Input
	def y(self):
		pass

	@property
	def mode(self):
		"""read self.x and compute mode"""
		pass

	def __call__(self):
		"""needs full reference signal, including derivatives"""
		x1, x2, x3, x4 = self.x
		u_eq = 0.0
		u_d = 0.0
		return u_eq + u_d


class FBLNoObsrv:
	def __init__(self):
		self.plant = Motor([1.0]*4)
		self.controller = FBLController(self.plant)
		self.prefilter = ReferenceFilter(0.0, (244, 117.2, 18.75))
		self.time = 0.0
		self.output_labels = ['reference angle', 'filtered reference',
							  'motor angle']

	def __len__(self):
		return len(self.plant) + len(self.prefilter)

	def __call__(self):
		q = self.prefilter.state[0]
		qdot = self.prefilter(self.reference())
		full_reference = [q] + qdot
		full_output = self.plant.output
		u = self.controller(full_reference, full_output)
		xdot = self.plant(u, 0.0) #disturbance assumed 0
		return xdot + qdot

	@property
	def state(self):
		return self.plant.state + self.prefilter.state

	@state.setter
	def state(self, x):
		n = len(self.plant)
		self.plant.state = x[:n]
		self.prefilter.state = x[n:]
		self.controller.state = self.plant.state

	def reference(self):
		return 0.0 if self.time < 1.0 else 2.0

	@property
	def output(self):
		return [self.reference(), self.prefilter.state[0], self.plant.output[0]]

	def plot(self):
		plt.figure()
		#Use descriptors for labels?
		for i, ilabel in enumerate(self.output_labels):
			plt.plot(self.t_out, self.y_out[:,i], label=ilabel)
		plt.show()
	

class FBLObsrv(FBLNoObsrv):
	def __init__(self):
		FBLNoObserv.__init__(self)
		self.observer = Observer(self.plant)
		self.output_labels.append('estimated angle')

	def __len__(self):
		return len(self.plant) + len(self.prefilter) + len(self.observer)
	
	def __call__(self):
		q = self.prefilter.state[0]
		qdot = self.prefilter(self.reference())
		full_reference = [q] + qdot
		full_output = self.plant.output
		u - self.controller(full_reference, full_output)
		xdot = self.plant(u, 0.0) #disturbance assumed 0
		xhatdot = self.observer(full_output, u)
		return xdot

	@FBLNoObsrv.state.getter
	def state(self):
		return self.plant.state + self.prefilter.state + self.observer.state

	@FBLNoObsrv.state.setter
	def state(self, x):
		n = len(self.plant)
		m = len(self.prefilter)
		self.plant.state = x[:n]
		self.prefilter.state = x[n:(n+m)]
		self.observer.state = x[(n+m):]
		self.controller.state = self.observer.state

	@property
	def output(self):
		return [self.reference(), self.prefilter.state[0], 
				self.plant.output[0], self.observer.output[0]] 


class SMCObsrv(FBLObsrv):
	def __init__(self):
		self.plant = Motor([1.0]*4)
		self.controller = SMController(self.plant)
		self.prefilter = ReferenceFilter(0.0, (244, 117.2, 18.75))
		self.observer = Observer(self.plant)


