# -*- coding: utf-8 -*-
"""
Illustration of fit routine used for the evaluation of my measurement data.
@author: mhart

ACB: the csv files to be read by this script can be generated from the RMT
TA_spect_len_0001_z files using the makedf.py utility. The csv files should then
be named int1.3.csv (for intensity 1.3) and all stored in the same directory.
This script can then be run in that directory to do the fitting.
"""

#-----------------------------------------------------------------------
#                    Imports
#-----------------------------------------------------------------------
import numpy as np
from scipy.optimize import curve_fit
from scipy.constants import physical_constants as constants
import pandas as pd
import sys
import matplotlib.pyplot as plt



#-----------------------------------------------------------------------
#                   Pseudo Code
#-----------------------------------------------------------------------
def get_energy_axis():
    your_energy_axis = np.linspace(51.012496,67.000271,1962)
    return your_energy_axis

def getOD(intensity):
    """ Returns a whole time delay scan at a given intensity.
        Shape (td_axis_size, energy_axis_size). """
    fname = "int"+str(intensity)+".csv"
    df = pd.read_csv(fname)
    time_delay_axis = np.array([float(x) for x in df.columns])
    return df.transpose().values, time_delay_axis

def get_intensities():
    return [1.3,1.6,1.9,2.2,2.5]

def get_roi(energy_axis,erange=(55.15,57.45)):
    for i,e in enumerate(energy_axis): 
        if e>erange[0]:
            first = i
            break
    for i,e in enumerate(energy_axis): 
        if e>erange[1]:
            last = i
            break

    return (first,last)
#-----------------------------------------------------------------------
#                   Constants
#-----------------------------------------------------------------------
path_length_density_product = 3e16 # in cm^-2  <-- estimated by OD and cross-section of T1 lines at iris 55
pldp_au = 0.77              # path-length-density-product in atomic units
alpha = constants['fine-structure constant'][0]
lineshape_constant = pldp_au/np.log(10)*4*np.pi*alpha
gamma_xe1 = 0.122 # from literature (Anderson 2001 I think?)

# resonance energies after calibration
# (retrieved by fitting a Lorentzian to the spectra far out of temporal overlap)
e_res = [55.38, 55.98, 57.27]

# set region of interest for fit
roi = slice(*get_roi(get_energy_axis()))
photonenergy = get_energy_axis()[roi]
#print (photonenergy)

# list of your intensity values
intensities = get_intensities()

#-----------------------------------------------------------------------
#                   Functions
#-----------------------------------------------------------------------
def wrap(phase, offset=0):
    """ Opposite of np.unwrap. Restrict phase to [-2*pi, 2*pi]. """
    return ( phase + np.pi + offset) % (2 * np.pi ) - np.pi - offset

def DCM_lineshape(energy_axis, z, phi, resonance_energy, gamma):
    """
    Dipole control model (DCM) line shape function for a single absorption line

    Parameters
    ----------
    energy_axis : the array of values that defines the photon energy axis
    z : line strength
    phi : dipole phase
    resonance_energy : resonance energy of the absorption line
    gamma : line width

    Returns
    -------
    np.array size of energy axis
        line shape function as a function of photon energy
    """
    lineshape = (gamma/2*np.cos(phi) - (energy_axis-resonance_energy)*np.sin(phi)) / ((energy_axis-resonance_energy)**2 + gamma**2/4)
    return  z * lineshape

def fit_lineshapes(energy_axis, *params):
    """
    Fit function to extract line shape parameters from several absorption lines 
    from the measurement data. I omitted the convolution with the experimental 
    spectral resolution which only marginally affects the fit results anyway.

    Parameters
    ----------
    energy_axis : the array of values that defines the photon energy axis
    *params : list of fit parameters, size: 3*N + 1 where N is the number of lines

    Returns
    -------
    model : np.array size of energy axis
        Calculates an optical density as a function of photon energy by adding
        up the line shape functions of N absorption lines. Includes a constant
        offset to fit the non-resonant background.
    """
    model = np.zeros(energy_axis.shape)
    z = params[:-1:3]
    phi = params[1:-1:3]
    gamma = params[2:-1:3]
    for e, energy in enumerate(e_res):
        model += DCM_lineshape(energy_axis, z[e]*gamma[e], phi[e], energy, gamma[e])
    model *= energy_axis* lineshape_constant
    model += params[-1] # add non-resonant background
    return model

#-----------------------------------------------------------------------
#                   Fit setup
#-----------------------------------------------------------------------

lower_bounds = [1e-6,  -2*np.pi, 0.4*gamma_xe1]*3 + [-15]
upper_bounds = [np.inf, 2*np.pi, 2.7*gamma_xe1]*3 + [20]
bounds = (lower_bounds, upper_bounds)

p_initial = [1, 0, gamma_xe1]*3 + [0]
# initial_model = fit_lineshapes(photonenergy, *p_initial)
optimum = []
fit_errs = []
td = []

#-----------------------------------------------------------------------
#                   Fit loop
#-----------------------------------------------------------------------

df=pd.DataFrame()

for i,intensity in enumerate(intensities):
    """ Outer loop over all intensities """
    
    OD,time_delay_axis = getOD(intensity)
    # my data is ordered from late TDs to early TDs. To initialize the fit
    # I first average over e.g. the region from 6 to 8 fs and extract robust 
    # start values for the inner loop that fits all time-delay spectra sequentially.
    # time_delay_axis[0]=8
    # time_delay_axis[n_late_td]=6
    freq_marginal = np.mean(OD[:7], axis=0)
    
    p_init, pcov = curve_fit(fit_lineshapes, photonenergy, freq_marginal[roi],
                             p_initial)
    params = []
    errors = []
    
    for s,spectrum in enumerate(OD):
        """ Inner loop over all time delays in a scan.
            This allows to use the fit parameters of the previous fit as initial
            parameters of the following fit which makes it more robust as the
            line strength decreases.                
        """
        print('{:.1f}  {}'.format(intensity, s))
        
        # restrict fit parameters to resonable values
        p_init[1:-1:3] = wrap(p_init[1:-1:3])
        p_init[:-1:3] = abs(p_init[:-1:3])
        p_init[2:-1:3] = abs(p_init[2:-1:3])

        # perform fit
        popt, pcov = curve_fit(fit_lineshapes,
                               photonenergy, spectrum[roi],
                               p_init, bounds=bounds)
        
        params.append(popt)
        errors.append(np.sqrt(np.abs(np.diag(pcov))))
        
        # reuse fit result in next iteration
        p_init = popt
    
    optimum.append(params)
    fit_errs.append(errors)


# fit results
# shape (len(intensities), time_delay_size, N_params)
opt_params = np.array(optimum)
err_params = np.array(fit_errs)
df["time"] = time_delay_axis[::-1]
for ii,intens in enumerate(intensities):
    for num in range(3):
#    plt.plot(time_delay_axis[::-1],opt_params[ii,::-1,1],label=str(intens))
        z0="T"+str(num+1)+"_z0"+str(intens)
        phi="T"+str(num+1)+"_phi"+str(intens)
        gam="T"+str(num+1)+"_gam"+str(intens)
        df[z0] = opt_params[ii,::-1,3*num]
        df[phi] = opt_params[ii,::-1,3*num+1]
        df[gam] = opt_params[ii,::-1,3*num+2]

df.to_csv("op.csv",index=False)

#plt.legend()
#plt.show()

