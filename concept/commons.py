# This file is part of CONCEPT, the cosmological N-body code in Python.
# Copyright (C) 2015 Jeppe Mosgard Dakin.
#
# CONCEPT is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# CONCEPT is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with CONCEPT. If not, see http://www.gnu.org/licenses/
#
# The auther of CONCEPT can be contacted at
# jeppe.mosgaard.dakin(at)post.au.dk
# The latest version of CONCEPT is available at
# https://github.com/jmd-dk/concept/



# This module contains imports, Cython declarations and values
# of parameters common to all other modules. Each module should have
# 'from commons import *' as its first statement.

############################################
# Imports common to pure Python and Cython #
############################################
from __future__ import division  # Needed for Python3 division in Cython
# Modules
import contextlib, cython, imp, matplotlib, numpy as np, os, re, shutil
import sys, unicodedata
# For math
from numpy import (arange, array, asarray, concatenate, cumsum, delete,
                   empty, linspace, ones, trapz, unravel_index, zeros)
from numpy.random import random
# Use a matplotlib backend that does not require a running X-server
matplotlib.use('Agg')
# Import h5py. This has to be done after importing matplotlib, as this
# somehow makes libpng unable to find the zlib shared library.
import h5py
# For fancy terminal output
from blessings import Terminal
terminal = Terminal(force_styling=True)
terminal.CONCEPT = 'CO\x1b[3mN\x1b[23mCEPT'
# For timing
from time import time
from datetime import timedelta
# For development purposes only
from time import sleep



#############
# MPI setup #
#############
from mpi4py import MPI
cython.declare(master='bint',
               nprocs='int',
               rank='int',
               )
# Functions for communication
comm = MPI.COMM_WORLD
Abort = comm.Abort
Allgather = comm.Allgather
Allgatherv = comm.Allgatherv
Allreduce = comm.Allreduce
Barrier = comm.Barrier
Bcast = comm.Bcast
Gather = comm.Gather
Gatherv = comm.Gatherv
Isend = comm.Isend
Reduce = comm.Reduce
Recv = comm.Recv
Scatter = comm.Scatter
Send = comm.Send
Sendrecv = comm.Sendrecv
allreduce = comm.allreduce
reduce = comm.reduce
sendrecv = comm.sendrecv
# Number of processes started with mpiexec
nprocs = comm.size
# The unique rank of the running process
rank = comm.rank
# Flag identifying the master/root process (that which have rank 0)
master = not rank



########################################
# Cython and pure Python related stuff #
########################################
# C type names to Numpy dtype names
cython.declare(C2np='dict')
C2np = {# Booleans
        'bint': np.bool,
        # Integers
        'char'         : np.byte,
        'short'        : np.short,
        'int'          : np.intc,
        'long int'     : np.long,
        'long long int': np.longlong,
        'ptrdiff_t'    : np.intp,
        # Unsgined integers
        'unsigned char'         : np.ubyte,
        'unsigned short'        : np.ushort,
        'unsigned int'          : np.uintc,
        'unsigned long int'     : np.uint,
        'unsigned long long int': np.ulonglong,
        'size_t'                : np.uintp,
        # Floating-point numbers
        'float'     : np.single,
        'double'    : np.double,
        'long float': np.longfloat,
        }
# In NumPy, binary operations between some unsigned int types (unsigned
# long int, unsigned long long int, size_t) and signed int types results
# in a double, rather than a signed int.
# Get around this bug by never using these particular unsigned ints.
if not cython.compiled:
    C2np['unsigned long int'] = C2np['long int']
    C2np['unsigned long long int'] = C2np['long long int']
    C2np['size_t'] = C2np['ptrdiff_t']
# Declarations exclusively to either pure Python or Cython
if not cython.compiled:
    # No-op decorators for Cython compiler directives
    def dummy_decorator(*args, **kwargs):
        if len(args) == 1 and len(kwargs) == 0 and callable(args[0]):
            # Called as @dummy_decorator. Return function
            return args[0]
        else:
            # Called as @dummy_decorator(*args, **kwargs).
            # Return decorator
            return dummy_decorator
    # Already builtin: cfunc, inline, locals, returns
    for directive in ('boundscheck',
                      'cdivision',
                      'initializedcheck',
                      'wraparound',
                      'header',
                      ):
        setattr(cython, directive, dummy_decorator)
    # Dummy Cython functions
    for func in ('address', ):
        setattr(cython, func, lambda _: _)
    # C allocation syntax for memory management
    def sizeof(dtype):
        # C dtype names to Numpy dtype names
        if dtype in C2np:
            dtype = C2np[dtype]
        elif dtype in ('func_b_ddd',
                       'func_d_dd',
                       'func_d_ddd',
                       'func_ddd_ddd',
                       ):
            dtype='object'
        elif dtype[-1] == '*':
            # Allocate pointer array of pointers (eg. int**).
            # Emulate these as lists of arrays.
            return [empty(1, dtype=sizeof(dtype[:-1]).dtype)]
        elif master:
            msg = dtype + ' not implemented as a Numpy dtype in commons.py'
            raise TypeError(msg)
        return array([1], dtype=dtype)
    def malloc(a):
        if isinstance(a, list):
            # Pointer to pointer represented as list of arrays
            return a
        return empty(a[0], dtype=a.dtype)
    def realloc(p, a):
        # Reallocation of pointer assumed
        p.resize(a[0], refcheck=False)
        return p
        #new_a = empty(a[0], dtype=a.dtype)
        #if new_a.size >= p.size:
        #    new_a[:p.size] = p
        #else:
        #    new_a[:] = p[:new_a.size]
        #return new_a
    def free(a):
        pass
    # Casting
    def cast(a, dtype):
        match = re.search('(.*)\[', dtype)
        if match:
            # Pointer to array cast assumed
            # (array to array in pure Python).
            return a
        else:
            # Scalar
            return C2np[dtype](a)
    # Dummy fused types
    number = number2 = integer = floating = []
else:
    # Lines in triple quotes will be executed in .pyx files
    """
    # Get full access to all of Cython
    cimport cython
    # GNU Scientific Library
    from cython_gsl cimport *
    # Mathematical functions
    from libc.math cimport round
    # Import the signed integer type ptrdiff_t
    from libc.stddef cimport ptrdiff_t
    # Functions for manual memory management
    from cpython.mem cimport PyMem_Malloc, PyMem_Realloc, PyMem_Free
    # Function type definitions of the form func_returntype_argumenttypes
    ctypedef bint    (*func_b_ddd)  (double, double, double)
    ctypedef double  (*func_d_dd)   (double, double)
    ctypedef double  (*func_d_ddd)  (double, double, double)
    ctypedef double* (*func_ddd_ddd)(double, double, double)
    # Create a fused number type containing all necessary numerical types
    ctypedef fused number:
        cython.int
        cython.size_t
        cython.float
        cython.double
    # Create another fused number type, so that function arguments can have
    # different specializations.
    ctypedef fused number2:
        cython.int
        cython.size_t
        cython.float
        cython.double
    # Create integer and floating fused types
    ctypedef fused integer:
        cython.int
        cython.size_t
    ctypedef fused floating:
        cython.float
        cython.double
    # Custom classes
    from species cimport Particles
    from IO cimport StandardSnapshot, GadgetSnapshot
    """

# Seperate but equivalent imports and
# definitions in pure Python and Cython
if not cython.compiled:
    # Mathematical constants and functions
    from numpy import (pi as π,
                       sin,  cos,  tan,  arcsin,  arccos,  arctan,
                       sinh, cosh, tanh, arcsinh, arccosh, arctanh,
                       exp, log, log2, log10,
                       sqrt,
                       )
    from math import erfc
    # Dummy unicode function
    def unicode(c):
        return c
else:
    # Lines in triple quotes will be executed in .pyx files.
    """
    # Mathematical constants and functions
    from libc.math cimport (M_PI as π,
                            sin, cos, tan,
                            asin as arcsin, 
                            acos as arccos, 
                            atan as arctan,
                            sinh, cosh, tanh,
                            asinh as arcsinh, 
                            acosh as arccosh, 
                            atanh as arctanh,
                            exp, log, log2, log10,
                            sqrt, erfc
                            )
    # The pyxpp script convert all Unicode source code characters into
    # ASCII. The function below grants the code access to
    # Unicode string literals, by undoing the convertion.
    @cython.header(c='str', returns='str')
    def unicode(c):
        return unicodedata.lookup(c.replace('_', ' '))
    """



##################
# Physical units #
##################
# Implement units as an instance of a Cython extension type with
# the actual units defined as data attributes.
@cython.cclass
class Units:
    # Initialization method.
    @cython.header
    def __init__(self):
        # The triple quoted string below serves as the type declaration
        # for the Units type. It will get picked up by the
        # pyxpp script and indluded in the .pxd files.
        """
        # Data attributes
        double cm, m, km, AU, pc, kpc, Mpc, Gpc
        double s, min, hr, day, yr, kyr, Myr, Gyr
        double g, kg, m_sun, km_sun, Mm_sun, Gm_sun
        """
        # The following is chosen as the base units:
        # Length: 1*kpc
        # Time:   1*Gyr
        # Mass:   1e+10*m_sun (1 m_sun ≡ 1.989e+30 kg)
        # Note that the base unit of velocity is then just about 1 km/s
        self.kpc    = 1
        self.Gyr    = 1
        self.m_sun  = 1e-10
        # Other prefixes of the base length, time and mass
        self.pc     = 1e-3*self.kpc
        self.Mpc    = 1e+6*self.pc
        self.Gpc    = 1e+9*self.pc
        self.yr     = 1e-9*self.Gyr
        self.kyr    = 1e+3*self.yr
        self.Myr    = 1e+6*self.yr
        self.km_sun = 1e+3*self.m_sun
        self.Mm_sun = 1e+6*self.m_sun
        self.Gm_sun = 1e+9*self.m_sun
        # Non-base units
        self.AU     = π/(60*60*180)*self.pc
        self.m      = self.AU/149597870700
        self.cm     = 1e-2*self.m
        self.km     = 1e+3*self.m
        self.day    = self.yr/365.25
        self.hr     = self.day/24
        self.min    = self.hr/60
        self.s      = self.min/60  # Uses Julian years
        self.kg     = self.m_sun/1.989e+30
        self.g      = 1e-3*self.kg
cython.declare(units='Units')
units = Units()



###########################################
# Absolute paths to directories and files #
###########################################
# The paths are stored in the top_dir/.paths file
cython.declare(paths='dict')
top_dir = os.path.abspath('.')
while True:
    if '.paths' in os.listdir(top_dir):
        break
    elif master and top_dir == '/':
        raise Exception('Cannot find the .paths file!')
    top_dir = os.path.dirname(top_dir)
paths_module = imp.load_source('paths', top_dir + '/.paths')
paths = {key: value for key, value in paths_module.__dict__.items()
         if isinstance(key, str) and not key.startswith('__')}



##########################
# Command line arguments #
##########################
# Handle command line arguments given to the Python interpreter
# (not those explicitly given to the run script).
# Construct a dict from command line arguments of the form
# "params='/path/to/params'"
cython.declare(argd='dict',
               globals_dict='dict',
               scp_password='str',
               )
argd = {}
for arg in sys.argv:
    with contextlib.suppress(Exception):
        exec(arg, argd)
globals_dict = {}
exec('', globals_dict)
for key in globals_dict.keys():
    argd.pop(key, None)
# Extract command line arguments from the dict. If not given,
# give the arguments some default value.
# The parameter file
paths['params'] = argd.get('params', '')
paths['params_dir'] = ('' if not paths['params']
                       else os.path.dirname(paths['params']))
# The scp password
scp_password = argd.get('scp_password', '')



################################################################
# Import all user specified parameters from the parameter file #
################################################################
# Dict constituting the namespace for the statements
# in the user specified parameter file.
params = {# The paths dict
          'paths': paths,
          # Modules
          'numpy': np,
          'np'   : np,
          'os'   : os,
          're'   : re,
          'sys'  : sys,
          # Units from the units extension type
          'cm'    : units.cm,
          'm'     : units.m,
          'km'    : units.km,
          'AU'    : units.AU,
          'pc'    : units.pc,
          'kpc'   : units.kpc,
          'Mpc'   : units.Mpc,
          'Gpc'   : units.Gpc,
          's'     : units.s,
          'yr'    : units.yr,
          'kyr'   : units.kyr,
          'Myr'   : units.Myr,
          'Gyr'   : units.Gyr,
          'g'     : units.g,
          'kg'    : units.kg,
          'm_sun' : units.m_sun,
          'km_sun': units.km_sun,
          'Mm_sun': units.Mm_sun,
          'Gm_sun': units.Gm_sun,
          # Mathemtical NumPy functions and constants
          'abs'        : np.abs,
          'arccos'     : np.arccos,
          'arccosh'    : np.arccosh,
          'arcsin'     : np.arcsin,
          'arcsinh'    : np.arcsinh,
          'arctan'     : np.arctan,
          'arctanh'    : np.arctanh,
          'cos'        : np.cos,
          'cosh'       : np.cosh,
          'exp'        : np.exp,
          'mod'        : np.mod,
          'sin'        : np.sin,
          'sinh'       : np.sinh,
          'sqrt'       : np.sqrt,
          'tan'        : np.tan,
          'tanh'       : np.tanh,
          'log'        : np.log,
          'log2'       : np.log2,
          'log10'      : np.log10,
          'pi'         : np.pi,
          unicode('π') : np.pi,
          'e'          : np.e,
          # Other NumPy functions
          'arange'     : np.arange,
          'array'      : np.array,
          'asarray'    : np.asarray,
          'concatenate': np.concatenate,
          'cumprod'    : np.cumprod,
          'cumsum'     : np.cumsum,
          'empty'      : np.empty,
          'linspace'   : np.linspace,
          'loadtxt'    : np.loadtxt,
          'max'        : np.max,
          'min'        : np.min,
          'ones'       : np.ones,
          'prod'       : np.prod,
          'random'     : np.random.random,
          'sum'        : np.sum,
          'trapz'      : np.trapz,
          'zeros'      : np.zeros,
          }
# "Import" the parameter file be executing it in the namespace defined
# by the params dict.
if os.path.isfile(paths['params']):
    with open(paths['params'], encoding='utf-8') as params_file:
        exec(params_file.read(), params)
# The parameters are now being processed as follows:
# - Some parameters are explicitly casted.
# - Spaces are removed from the 'snapshot_type' parameter, and all
#   characters are converted to lowercase.
# - The 'output_times' are sorted and duplicates (for each type of
#   output) are removed.
# - Paths below or just one level above the concept directory are made
#   relative to this directory in order to reduce screen clutter.
# - Colors are transformed to (r, g, b) arrays.
# - The 'special_params' parameter is set to an empty dictionary if it
#   is not defined in params.py
cython.declare(# Input/output
               IC_file='str',
               snapshot_type='str',
               output_dirs='dict',
               output_bases='dict',
               output_times='dict',
               # Numerical parameter
               boxsize='double',
               ewald_gridsize='size_t',
               PM_gridsize='ptrdiff_t',
               P3M_scale='double',
               P3M_cutoff='double',
               softeningfactors='dict',
               Δt_factor='double',
               # Cosmological parameters
               H0='double',
               Ωm='double',
               ΩΛ='double',
               a_begin='double',
               # Graphics
               color='double[::1]',
               bgcolor='double[::1]',
               resolution='unsigned int',
               liverender='str',
               remote_liverender='str',
               terminal_colormap='str',
               terminal_resolution='unsigned int',
               # Simlation options
               use_Ewald='bint',
               kick_algorithms='dict',
               special_params='dict',
               )
# Input/output
IC_file = str(params.get('IC_file', 'ICs/default'))
if (IC_file and not os.path.relpath(IC_file, paths['concept_dir'])
                            .startswith('../../')):
    IC_file = os.path.relpath(IC_file, paths['concept_dir'])
snapshot_type = (str(params.get('snapshot_type', 'standard'))
                 .lower().replace(' ', ''))
output_dirs = dict(params.get('output_dirs', {}))
for kind in ('snapshot', 'powerspec', 'render'):
    output_dirs[kind] = str(output_dirs.get(kind, 'output'))
output_dirs = {key: path if not path 
                            or os.path.relpath(path, paths['concept_dir'])
                                       .startswith('../../')
                         else os.path.relpath(path, paths['concept_dir']) 
               for key, path in output_dirs.items()}
output_bases = dict(params.get('output_bases', {}))
for kind in ('snapshot', 'powerspec', 'render'):
    output_bases[kind] = str(output_bases.get(kind, kind))
output_times = dict(params.get('output_times', {}))
for kind in ('snapshot', 'powerspec', 'render', 'terminal render'):
    output_times[kind] = output_times.get(kind, ())
output_times = {key: tuple(sorted(set([float(nr) for nr in np.ravel(val)
                                                 if nr or nr == 0])))
                for key, val in output_times.items()}
# Numerical parameters
boxsize = float(params.get('boxsize', 1))
ewald_gridsize = int(params.get('ewald_gridsize', 64))
PM_gridsize = int(params.get('PM_gridsize', 64))
P3M_scale = float(params.get('P3M_scale', 1.25))
P3M_cutoff = float(params.get('P3M_cutoff', 4.8))
softeningfactors = dict(params.get('softeningfactors', {}))
for kind in ('dark matter', ):
    softeningfactors[kind] = float(softeningfactors.get(kind, 0.03))
Δt_factor = float(params.get(unicode('Δ') + 't_factor', 0.01))
# Cosmological parameters
H0 = float(params.get('H0', 70*units.km/(units.s*units.Mpc)))
Ωm = float(params.get(unicode('Ω') + 'm', 0.3))
ΩΛ = float(params.get(unicode('Ω') + unicode('Λ'), 0.7))
a_begin = float(params.get('a_begin', 0.02))
# Graphics
color = array(matplotlib.colors.ColorConverter()
              .to_rgb(params.get('color', 'lime')), dtype='float64')
bgcolor = array(matplotlib.colors.ColorConverter()
                .to_rgb(params.get('bgcolor', 'black')), dtype='float64')
resolution = int(params.get('resolution', 1080))
liverender = str(params.get('liverender', ''))
if liverender:
    if (not os.path.relpath(liverender, paths['concept_dir'])
                    .startswith('../../')):
        liverender = os.path.relpath(liverender, paths['concept_dir'])
    if not liverender.endswith('.png'):
        liverender += '.png'
remote_liverender = str(params.get('remote_liverender', ''))
if remote_liverender and not remote_liverender.endswith('.png'):
    remote_liverender += '.png'
terminal_colormap = str(params.get('terminal_colormap', 'gnuplot2'))
terminal_resolution = int(params.get('terminal_resolution', 80))
# Simulation options
kick_algorithms = dict(params.get('kick_algorithms', {}))
for kind in ('dark matter', ):
    kick_algorithms[kind] = str(kick_algorithms.get(kind, 'PP'))
use_Ewald = bool(params.get('use_Ewald', True))
# Extra hidden parameters via the special_params variable
special_params = dict(params.get('special_params', {}))



#####################################
# Global (module level) allocations #
#####################################
# Useful for temporary storage of 3D vector
cython.declare(vector='double*',
               vector_mv='double[::1]',
               )
vector = malloc(3*sizeof('double'))
vector_mv = cast(vector, 'double[:3]')

################
# Pure numbers #
################
cython.declare(minus_4π='double',
               one_third='double',
               one_twelfth='double',
               sqrt_π='double',
               two_π='double',
               two_thirds='double',
               )
minus_4π = -4*π
one_third = 1.0/3.0
one_twelfth = 1.0/12.0
sqrt_π = sqrt(π)
two_thirds = 2.0/3.0
two_π = 2*π



############################################
# Derived and internally defined constants #
############################################
cython.declare(a_dumps='tuple',
               a_max='double',
               G_Newton='double',
               PM_gridsize3='ptrdiff_t',
               PM_gridsize_padding='ptrdiff_t',
               boxsize2='double',
               boxsize3='double',
               ewald_file='str',
               half_PM_gridsize='ptrdiff_t',
               half_PM_gridsize_padding='ptrdiff_t',
               half_boxsize='double',
               machine_ϵ='double',
               minus_half_boxsize='double',
               powerspec_dir='str',
               powerspec_base='str',
               powerspec_times='tuple',
               recp_boxsize2='double',
               render_dir='str',
               render_base='str',
               render_times='tuple',
               scp_host='str',
               snapshot_dir='str',
               snapshot_base='str',
               snapshot_times='tuple',
               terminal_render_times='tuple',
               two_ewald_gridsize='int',
               two_machine_ϵ='double',
               two_recp_boxsize='double',
               use_PM='bint',
               ϱ='double',
               ϱm='double',
               PM_fac_const='double',
               longrange_exponent_fac='double',
               P3M_cutoff_phys='double',
               P3M_scale_phys='double',
               π_recp_PM_gridsize='double',
               )
# List of dump times
a_dumps = tuple(sorted(set([nr for val in output_times.values()
                               for nr in val])))
# The scale factor at the last time step
a_max = a_begin if len(a_dumps) == 0 else np.max(a_dumps)
# Extract output variables from output dicts
snapshot_dir          = output_dirs['snapshot']
snapshot_base         = output_bases['snapshot']
snapshot_times        = output_times['snapshot']
powerspec_dir         = output_dirs['powerspec']
powerspec_base        = output_bases['powerspec']
powerspec_times       = output_times['powerspec']
render_dir            = output_dirs['render']
render_base           = output_bases['render']
render_times          = output_times['render']
terminal_render_times = output_times['terminal render']
# Newtons constant
G_Newton = 6.6738e-11*units.m**3/units.kg/units.s**2
# The average, comoing density (the critical
# comoving density since we only study flat universes)
ϱ = 3*H0**2/(8*π*G_Newton)
# The average, comoving matter density
ϱm = Ωm*ϱ
PM_gridsize3 = PM_gridsize**3
PM_gridsize_padding = 2*(PM_gridsize//2 + 1)
half_PM_gridsize = PM_gridsize//2
half_PM_gridsize_padding = PM_gridsize_padding//2
boxsize2 = boxsize**2
boxsize3 = boxsize**3
recp_boxsize2 = 1/boxsize2
half_boxsize = 0.5*boxsize
minus_half_boxsize = -half_boxsize
two_recp_boxsize = 2/boxsize
π_recp_PM_gridsize = π/PM_gridsize
# Name of file storing the Ewald grid
ewald_file = '.ewald_gridsize=' + str(ewald_gridsize) + '.hdf5'
# Machine epsilon
machine_ϵ = np.finfo('float64').eps
two_ewald_gridsize = 2*ewald_gridsize
two_machine_ϵ = 2*machine_ϵ
# Flag specifying whether the PM method is used or not
use_PM = False
if (set(('PM', 'P3M')) & set(kick_algorithms.values())
    or powerspec_times):
    use_PM = True
# All constant factors across the PM scheme is gathered in the PM_fac
# variable. It's contributions are:
# For CIC interpolating particle masses/volume to the grid points:
#     particles.mass/(boxsize/PM_gridsize)**3
# Factor in the Greens function:
#     -4*π*G_Newton/((2*π/((boxsize/PM_gridsize)*PM_gridsize))**2)   
# From finite differencing to get the forces:
#     -PM_gridsize/boxsize
# For converting acceleration to momentum
#     particles.mass*Δt
# Everything except the mass and the time are constant, and is condensed
# into the PM_fac_const variable.
PM_fac_const = G_Newton*PM_gridsize**4/(π*boxsize**2)
# The exponential cutoff for the long-range force looks like
# exp(-k2*rs2). In the code, the wave vector is in grid units in stead
# of radians. The conversion is 2*π/PM_gridsize. The total factor on k2
# in the exponential is then
longrange_exponent_fac = -(2*π/PM_gridsize*P3M_scale)**2
# The short-range/long-range force scale
P3M_scale_phys = P3M_scale*boxsize/PM_gridsize
# Particles within this distance to the surface of the domain should
# interact with particles in the neighboring domain via the shortrange
# force, when the P3M algorithm is used.
P3M_cutoff_phys = P3M_scale_phys*P3M_cutoff
# The host name in the 'remote_liverender' parameter
scp_host = (re.search('@(.*):', remote_liverender).group(1)
            if remote_liverender else '')



###########################################
# Customly defined mathematical functions #
###########################################
# When writing a function, remember to add its name to the tuple
# "commons_functions" in the "make_pxd" function in the "pyxpp.py" file.

# Abs function for numbers
if not cython.compiled:
    # Pure Python already have a generic abs function
    pass
else:
    """
    @cython.header(x=number,
                   returns=number,
                   )
    def abs(x):
        if x < 0:
            return -x
        return x
    """

# Max function for 1D memory views of numbers
if not cython.compiled:
    # Pure Python already have a generic max function
    pass
else:
    """
    @cython.header(returns=number)
    def max(number[::1] a):
        cdef:
            number m
            size_t N
            size_t i
        N = a.shape[0]
        m = a[0]
        for i in range(1, N):
            if a[i] > m:
                m = a[i]
        return m
    """

# Min function for 1D memory views of numbers
if not cython.compiled:
    # Pure Python already have a generic min function
    pass
else:
    """
    @cython.header(returns=number)
    def min(number[::1] a):
        cdef:
            number m
            size_t N
            size_t i
        N = a.shape[0]
        m = a[0]
        for i in range(1, N):
            if a[i] < m:
                m = a[i]
        return m
    """

# Modulo function for numbers
@cython.header(x=number,
               length=number2,
               returns=number,
               )
def mod(x, length):
    """Warning: mod(integer, floating) not possible. Note that
    no error will occur if called with illegal types!
    Note also that -length < x < 2*length must be true for this
    function to compute the modulo properly. A more general
    prescription would be x = (x % length) + (x < 0)*length.
    """
    if not (number in integer and number2 in floating):
        if x < 0:
            x += length
        elif x >= length:
            x -= length
        return x

# Sum function for 1D memory views of numbers
if not cython.compiled:
    # To correctly handle all numeric data types, use numpy's sum
    # function rather than Python's built-in sum function.
    sum = np.sum
else:
    """
    @cython.header(returns=number)
    def sum(number[::1] a):
        cdef:
            number Σ
            size_t N
            size_t i
        N = a.shape[0]
        if N == 0:
            return 0
        Σ = a[0]
        for i in range(1, N):
            Σ += a[i]
        return Σ
    """

# Prod function for 1D memory views of numbers
if not cython.compiled:
    # Utilize the prod function from numpy for pure Python
    prod = np.prod
else:
    """
    @cython.header(returns=number)
    def prod(number[::1] a):
        cdef:
            number Π
            size_t N
            size_t i
        N = a.shape[0]
        if N == 0:
            return 1
        Π = a[0]
        for i in range(1, N):
            Π *= a[i]
        return Π
    """

# Unnormalized sinc function (faster than gsl_sf_sinc)
@cython.header(x='double',
               y='double',
               returns='double',
               )
def sinc(x):
    y = sin(x)
    if y == x:
        return 1
    else:
        return y/x

# Function for printing messages as well as timed progress messages
def masterprint(msg, *args, indent=0, end='\n', **kwargs):
    global progressprint_time
    if not master:
        return
    if msg == 'done':
        # End of progress message
        interval = timedelta(seconds=(time() - progressprint_time)).__str__()
        if interval.startswith('0:'):
            # Less than an hour
            interval = interval[2:]
            if interval.startswith('00:'):
                # Less than a minute
                interval = interval[3:]
                if interval.startswith('00.'):
                    if interval[3:6] == '000':
                        # Less than a millisecond
                        interval = '< 1 ms'
                    else:
                        # Less than a second
                        interval = interval[3:6].lstrip('0') + ' ms'
                else:
                    # Between a second and a minute
                    if interval.startswith('0'):
                        # Between 1 and 10 seconds
                        if '.' in interval:
                            interval = (interval[1:(interval.index('.') + 2)]
                                        + ' s')
                    else:
                        # Between 10 seconds and a minute
                        if '.' in interval:
                            interval = interval[:interval.index('.')] + ' s'
            else:
                # Between a minute and an hour
                if interval.startswith('0'):
                    interval = interval[1:]
                if '.' in interval:
                    interval = interval[:interval.index('.')]
        else:
            # More than an hour
            if '.' in interval:
                interval = interval[:interval.index('.')]
        print(' done after ' + interval,
              *args, flush=True, **kwargs)
    else:
        # Create time stamp for use in progress message
        progressprint_time = time()
        # Print out message
        msg = str(msg).replace('CONCEPT', terminal.CONCEPT)
        args = [arg.replace('CONCEPT', terminal.CONCEPT)
                if isinstance(arg, str) else arg for arg in args]
        if ((args and isinstance(args[-1], str) and args[-1].endswith('...'))
            or not args and msg.endswith('...')):
            end = ''
        print(' '*indent + msg, *args, flush=True, end=end, **kwargs)

# Function for printing warnings
def masterwarn(msg, *args, indent=0, **kwargs):
    if not master:
        return
    msg = str(msg).replace('CONCEPT', terminal.CONCEPT)
    if args:
        args = [arg.replace('CONCEPT', terminal.CONCEPT)
                if isinstance(arg, str) else str(arg) for arg in args]
        print(terminal.bold_red(' '*indent + 'Warning: '
                                + ' '.join([msg] + args)),
                                file=sys.stderr,
                                flush=True,
                                **kwargs)
    else:
        print(terminal.bold_red(' '*indent + 'Warning: ' + msg),
              file=sys.stderr,
              flush=True,
              **kwargs)
