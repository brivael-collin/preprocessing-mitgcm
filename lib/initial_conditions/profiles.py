from datetime import datetime

import numpy as np
import xarray as xr

from .simstrat import download_simstrat_alplakes, parse_alplakes_1d_from_directory

# Constant salinity used everywhere at the start of the run [g/kg]
DEFAULT_INITIAL_SALT = 0.03


def create_initial_temperature_from_measure_profile(DzGrid, MeasureProfile, VariableName='temp'):
    """
    Interpolate a measured or simulated temperature profile onto the model layers.
    Inputs:
      DzGrid (np.ndarray)           - thickness of each vertical layer [m]
      MeasureProfile (xr.Dataset)   - profile with a 'depth' coordinate [m, positive downwards]
      VariableName (str)            - name of the temperature variable in MeasureProfile
    Output:
      (np.ndarray) - temperature at the bottom depth of each layer, same shape as DzGrid. Layers outside the
                     measured depth range take the nearest measured value.
    """
    # Depth of the bottom of each layer
    ZGrid = np.cumsum(DzGrid.flatten())

    # Linear interpolation to the layer depths, then fill depths outside the profile with the nearest value
    InterpolatedProfile = MeasureProfile.interp(depth=ZGrid, method='linear')
    FilledProfile = InterpolatedProfile.ffill(dim='depth').bfill(dim='depth')

    return FilledProfile[VariableName].values.reshape(DzGrid.shape)


def build_initial_conditions(Config, DzGrid, StartTimeInSecond):
    """
    Build the initial temperature and salinity profiles according to Config.InitializationType:
      - 'simstrat': Simstrat profile from Alplakes closest to the start date (downloaded into
                    1-preprocessing-inputs/simstrat_data/<lake> if missing), interpolated to the model layers
      - 'pickup':   restart from a MITgcm pickup file; the temperature is a dummy overwritten by the pickup
    Inputs:
      Config (ConfigObject)     - run settings (InitializationType, LakeName, StartDate, TimeStep, Paths.SimstratFolder)
      DzGrid (np.ndarray)       - thickness of each vertical layer [m]
      StartTimeInSecond (float) - start of the simulation [s from the reference date]
    Outputs:
      InitialTemperature (np.ndarray) - initial temperature of each layer [degC], same shape as DzGrid
      InitialSalt (np.ndarray)        - initial salinity of each layer [g/kg], same shape as DzGrid
      PickupNumber (str)              - 10-digit number of the pickup file, '' if not restarting from a pickup
    """
    InitialSalt = np.full(DzGrid.shape, DEFAULT_INITIAL_SALT)

    if Config.InitializationType == 'simstrat':
        # Simstrat profile closest to the start date, interpolated to the model layers
        StartDate = datetime.strptime(Config.StartDate, '%Y%m%d')
        download_simstrat_alplakes(Config.LakeName, StartDate, Config.Paths.SimstratFolder)
        SimstratTemperature = parse_alplakes_1d_from_directory(Config.Paths.SimstratFolder)
        MeasuredProfile = SimstratTemperature.sel(time=StartDate, method='nearest')
        print(f'Initial temperature from Simstrat profile of {MeasuredProfile.time.values}')
        return create_initial_temperature_from_measure_profile(DzGrid, MeasuredProfile), InitialSalt, ''

    if Config.InitializationType == 'pickup':
        # Pickup number = number of time steps since the reference date; T values are only placeholders
        PickupNumber = str(int(StartTimeInSecond / Config.TimeStep)).zfill(10)
        print(f'Restart from pickup file number {PickupNumber}')
        return np.zeros(DzGrid.shape), InitialSalt, PickupNumber

    raise ValueError(f'Unknown initialization type: {Config.InitializationType}')
