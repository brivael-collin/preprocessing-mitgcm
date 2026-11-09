from datetime import datetime

import numpy as np

from .datalakes import download_ctd_datalakes, parse_ctd_datalakes
from .simstrat import download_simstrat_alplakes, parse_alplakes_1d_from_directory

# Maximum time between the start date and the CTD profile before a warning is printed [days]
MAX_CTD_DELAY_DAYS = 31


def interpolate_profile_to_layers(DzGrid, Profile, VariableName):
    """
    Interpolate a measured or simulated vertical profile onto the model layers.
    Inputs:
      DzGrid (np.ndarray) - thickness of each vertical layer [m]
      Profile (xr.Dataset) - profile with a 'depth' coordinate [m, positive downwards]
      VariableName (str)   - name of the variable to interpolate (e.g. 'temp', 'salt')
    Output:
      (np.ndarray) - variable at the bottom depth of each layer, same shape as DzGrid. Layers outside the
                     measured depth range take the nearest measured value.
    """
    # Depth of the bottom of each layer
    ZGrid = np.cumsum(DzGrid.flatten())

    # Drop missing measurements, interpolate linearly to the layer depths, then fill the layers outside the
    # profile with the nearest value
    Variable = Profile[VariableName].dropna('depth')
    InterpolatedProfile = Variable.interp(depth=ZGrid, method='linear')
    FilledProfile = InterpolatedProfile.ffill(dim='depth').bfill(dim='depth')

    return FilledProfile.values.reshape(DzGrid.shape)


def get_ctd_profile(Config, StartDate):
    """
    CTD profile from Datalakes (Config.CtdFileId) closest in time to the start of the run. The file is
    downloaded into Config.Paths.CtdFolder if missing.
    Inputs:
      Config (ConfigObject) - run settings (CtdFileId, Paths.CtdFolder)
      StartDate (datetime)  - start of the simulation
    Output:
      (xr.Dataset) - variables 'temp' [degC] and 'salt' [PSU] along 'depth', at the closest measurement time
    """
    FilePath = download_ctd_datalakes(Config.CtdFileId, Config.Paths.CtdFolder)
    Profile = parse_ctd_datalakes(FilePath).sel(time=StartDate, method='nearest')

    # Tell which measurement is used, and warn if it is far from the start date
    DelayDays = abs((Profile.time.values - np.datetime64(StartDate)) / np.timedelta64(1, 'D'))
    print(f'CTD profile of {str(Profile.time.values)[:16]} ({DelayDays:.0f} days from the start date)')
    if DelayDays > MAX_CTD_DELAY_DAYS:
        print(f'WARNING: the closest CTD profile is more than {MAX_CTD_DELAY_DAYS} days from the start date')

    return Profile


def build_initial_conditions(Config, DzGrid, StartTimeInSecond):
    """
    Build the initial temperature and salinity profiles according to Config.InitializationType:
      - 'datalakes_ctd': temperature and salinity of the Datalakes CTD profile closest to the start date
                         (Canton Zug monitoring), interpolated to the model layers
      - 'simstrat':      temperature of the Simstrat profile (Alplakes) closest to the start date, salinity of
                         the closest CTD profile
      - 'pickup':        restart from a MITgcm pickup file; T and S are dummies overwritten by the pickup
    Inputs:
      Config (ConfigObject)     - run settings (InitializationType, LakeName, StartDate, TimeStep, CtdFileId,
                                  Paths.CtdFolder, Paths.SimstratFolder)
      DzGrid (np.ndarray)       - thickness of each vertical layer [m]
      StartTimeInSecond (float) - start of the simulation [s from the reference date]
    Outputs:
      InitialTemperature (np.ndarray) - initial temperature of each layer [degC], same shape as DzGrid
      InitialSalt (np.ndarray)        - initial salinity of each layer [PSU], same shape as DzGrid
      PickupNumber (str)              - 10-digit number of the pickup file, '' if not restarting from a pickup
    """
    StartDate = datetime.strptime(Config.StartDate, '%Y%m%d')

    if Config.InitializationType == 'datalakes_ctd':
        # Measured temperature and salinity, interpolated to the model layers
        CtdProfile = get_ctd_profile(Config, StartDate)
        return (interpolate_profile_to_layers(DzGrid, CtdProfile, 'temp'),
                interpolate_profile_to_layers(DzGrid, CtdProfile, 'salt'), '')

    if Config.InitializationType == 'simstrat':
        # Simstrat temperature closest to the start date (Simstrat has no salinity: measured one)
        download_simstrat_alplakes(Config.LakeName, StartDate, Config.Paths.SimstratFolder)
        SimstratTemperature = parse_alplakes_1d_from_directory(Config.Paths.SimstratFolder)
        SimstratProfile = SimstratTemperature.sel(time=StartDate, method='nearest')
        print(f'Initial temperature from Simstrat profile of {SimstratProfile.time.values}')
        CtdProfile = get_ctd_profile(Config, StartDate)
        return (interpolate_profile_to_layers(DzGrid, SimstratProfile, 'temp'),
                interpolate_profile_to_layers(DzGrid, CtdProfile, 'salt'), '')

    if Config.InitializationType == 'pickup':
        # Pickup number = number of time steps since the reference date; T and S values are only placeholders
        PickupNumber = str(int(StartTimeInSecond / Config.TimeStep)).zfill(10)
        print(f'Restart from pickup file number {PickupNumber}')
        return np.zeros(DzGrid.shape), np.zeros(DzGrid.shape), PickupNumber

    raise ValueError(f'Unknown initialization type: {Config.InitializationType}')
