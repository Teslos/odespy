from ODE import Solver, Adaptive, doc_string_table_of_parameters
import numpy as np
import inspect, sys

_parameters_RKC = dict(

    spcrad_f77 = dict(
        help='Intend to supply a Fortran subroutine as spcrad. '\
             'This subroutine should be defined in form:       '\
             '      double precision function spcrad_f77(neq,t,'\
             '     1       u)                                  '\
             'Cf2py intent(hide)  neq                          '\
             '      integer       neq                          '\
             '      double precision t,u(neq)                  '\
             '      spcrad_f77 =                               '\
             '      return                                     '\
             '      end                                        ',
        type=callable),
    )

import ODE
ODE._parameters.update(_parameters_RKC)

class RKC(Adaptive):
    '''
    Wrapper for rkc.f, which intends to integrates initial value problems for
    systems of first order ordinary differential equations. It is based on a
    family of explicit Runge-Kutta-Chebyshev formulas of order two.

    Source code for rkc.f can be obtained directly from website of netlib.
    '''
    _optional_parameters = Adaptive._optional_parameters + \
        ['f_f77', 'spcrad', 'spcrad_f77', 'jac_constant']
    # The following step parameters are illegal for rkc.f
    _optional_parameters.remove('first_step')
    _optional_parameters.remove('min_step')
    _optional_parameters.remove('max_step')

    _istate_messages = {\
    3: '''\
    Repeated improper error control: For some j, ATOL(j) = 0 and Y(j) = 0.''',
    4: '''\
    Unable to achieve the desired accuracy with the precision available.
    A severe lack of smoothness in the solution y(t) or the function
    f(t,y) is likely. ''',
    6: '''\
    The method used by RKC to estimate the spectral radius of the Jacobian
    failed to converge.''',
    0:'''Iteration stops when function TERMINATE return with True.''',
    1:'''Iteration succeed.'''}

    def set_parameter_properties(self):
        self._parameters['rtol']['type'] = float
        self._parameters['rtol']['range'] = (2.22e-15, 0.1)

    def check_atol(self):
        ''' ATOL need to be supplied as scalar or vector of length NEQ. '''
        atol = self.atol
        if not isinstance(atol,float):
            if len(atol) not in (1, self.neq):
                raise ValueError,  '''
ATOL =%s should be either a scalar or a vector of length NEQ=%d.
           ''' % (str(atol), self.neq)

    def valid_data(self):
        self.check_atol()
        return Adaptive.valid_data(self)

    def set_internal_parameters(self):
        # INFO(4) is an integer array to specify how the problem
        # would be solved
        self.info = np.zeros(4, int)

        self.info[0] = 1      # Compute solution at each time point.
        if hasattr(self, 'spcrad_f77') or hasattr(self, 'spcrad'):
            self.info[1] = 1  # SPCRAD is supplied.
        else:
            self.spcrad = lambda x,y: 0.0  # dummy function
        # whether Jacobian is known to be constant.
        self.info[2] = self.jac_constant
        if (np.iterable(self.atol) and (len(self.atol) == self.neq)):
            self.info[3] = 1   # ATOL is a sequence of length NEQ

        if hasattr(self, 'f'):  
            # If f is input in form of f(u,t), wrap f to f_f77 for Fortran code.
            f = self.f
            self.f_f77 = lambda t,u: np.asarray(f(u,t))
        elif hasattr(self, 'f_f77'):
            # If f is input in form of f(t,u) (usually in Fortran),
            # wrap f_f77 to the general form f(u,t) for switch_to()
            f_f77 = self.f_f77
            self.f = lambda u,t: np.asarray(f_f77(t,u))
        # If spcrad is input in form of spcrad(u,t), 
        # wrap spcrad to spcrad_f77 for Fortran code.
        if hasattr(self, 'spcrad'):  
            # If spcrad is in form of spcrad(u,t), wrap for Fortran code.
            spcrad = self.spcrad
            self.spcrad_f77 = lambda t,u: np.asarray(spcrad(u,t))
        Solver.set_internal_parameters(self)   # Common settings


    def solve(self, time_points, terminate=None):
        # flag to indicate dummy function
        itermin = int(terminate is not None)
        # Logical value cannot be transferred with f2py.
        if terminate is None:    # Dummy function
            terminate_int = lambda u, t, step_no, nt, neq: 0
        else:
            terminate_int = lambda u, t, step_no, nt, neq: \
                                   int(terminate(u, t, step_no))

        self.t = np.asarray(time_points)

        # Setting for internal parameters, (like self.u)
        self.set_internal_parameters()

        # Validity-check for values of class attributes
        if not self.valid_data():
            raise ValueError('Invalid data in "%s":\n%s' % \
                             (self.__class__.__name__,
                              pprint.pformat(self.__dict__)))

        # Call extension module
        from _rkc import solve
        # Fortran or Python function
        f = getattr(self.f_f77, '_cpointer', self.f_f77)
        spcrad = getattr(self.spcrad_f77, '_cpointer', self.spcrad_f77)

        # Start iteration
        uout, istate, nstop = solve(spcrad, f, self.u[0].copy(),
                                    self.t, self.rtol, self.atol, self.info,
                                    terminate_int, itermin)
        # Print corresponding message
        print self._istate_messages[istate]
        print 'Iteration stops at T=%g' % self.t[nstop-1]

        # Error occurs.
        if istate  > 1:   # Abnormal status
            sys.exit(1)   # Interrupt

        self.u = np.asarray(uout[:nstop,:]).copy()
        return self.u, self.t



class RKF45(Adaptive):
    """
    Wrapper for rkf45.f, a FORTRAN solver designed to solve non-stiff and
    mildly stiff differential equations by the well-known
    Runge-Kutta-Fehlberg (4,5) method.

    The FORTRAN source rkf45.f can be obtained from Netlib.
    """

    _optional_parameters = Adaptive._optional_parameters + ['f_f77']
    # The following step parameters are illegal for rkf45.f
    _optional_parameters.remove('first_step')
    _optional_parameters.remove('min_step')
    _optional_parameters.remove('max_step')

    def set_parameter_properties(self):
        self._parameters['rtol']['type'] = float
        self._parameters['rtol']['extra_check'] = lambda x: x >= 0.0
        self._parameters['atol']['type'] = float
        self._parameters['atol']['extra_check'] = lambda x: x >= 0.0

    def set_internal_parameters(self):
        if hasattr(self, 'f'):  
            # If f is input in form of f(u,t), wrap f to f_f77 for Fortran code.
            f = self.f
            self.f_f77 = lambda t,u: np.asarray(f(u,t))
        elif hasattr(self, 'f_f77'):
            # If f is input in form of f(t,u) (usually in Fortran),
            # wrap f_f77 to the general form f(u,t) for switch_to()
            f_f77 = self.f_f77
            self.f = lambda u,t: np.asarray(f_f77(t,u))
        Solver.set_internal_parameters(self)

    def advance(self):
        u, t, n, rtol, atol = self.u, self.t, self.n, self.rtol, self.atol

        from _rkf45 import advance
        f = getattr(self.f_f77, '_cpointer', self.f_f77)
        unew, istate = advance(f, u[n], t[n], t[n + 1], rtol, atol)
        if istate > 2:
            sys.exit(1)
        return unew

# Update doc strings with common info
class_, doc_str, classname = None, None, None
classes = [item[0] for item in locals().items() \
               if inspect.isclass(item[1])]
for classname in classes:
    class_ = eval(classname)
    doc_str = getattr(class_, '__doc__')
    setattr(class_, '__doc__', 
            doc_str + doc_string_table_of_parameters(class_, 
                                                     fixed_width=(21,49)))
del class_, doc_str, classname  # do not pollute namespace

