"""Filling of the !placeholder! tokens of the MITgcm template files (run_config/data*, code/SIZE.h, code/swfrac.F)."""
import glob
import os
from datetime import datetime
from pathlib import PurePosixPath

from lib.utils.io import modify_arguments

# Symlink created in run/ by launch_simulation.sh, pointing to the absolute results folder. The namelists use it
# because MITgcm truncates longer paths (diagnostics fileName is CHARACTER*80 in checkpoint67c)
RESULTS_LINK = 'results'


def get_run_times(Config):
    """
    Start and end of the simulation, in seconds from the reference date (MITgcm's time axis).
    Input:
      Config (ConfigObject) - run settings (StartDate, EndDate, ReferenceDate, as 'YYYYMMDD' strings)
    Outputs:
      StartTimeInSecond (float) - start of the simulation [s from the reference date]
      EndTimeInSecond (float)   - end of the simulation [s from the reference date]
    """
    ReferenceDate = datetime.strptime(Config.ReferenceDate, '%Y%m%d')
    StartTimeInSecond = (datetime.strptime(Config.StartDate, '%Y%m%d') - ReferenceDate).total_seconds()
    EndTimeInSecond = (datetime.strptime(Config.EndDate, '%Y%m%d') - ReferenceDate).total_seconds()
    return StartTimeInSecond, EndTimeInSecond


def get_mitgcm_results_folder(Config):
    """
    Absolute folder where MITgcm writes its results on the remote computer. The remote data folder RemoteRoot
    (e.g. /storage/lake_zug_transport) mirrors the local data layout:
      <RemoteRoot>/2-preprocessing-outputs/<SimulationName>/run   (MITgcm runs here)
      <RemoteRoot>/<ResultsFolder>/<SimulationName>                (results, e.g. ResultsFolder = '3-MITgcm-outputs')
    Input:
      Config (ConfigObject) - run settings (RemoteRoot (absolute), ResultsFolder (relative to RemoteRoot, or
                              absolute), SimulationName)
    Output:
      (str) - '<RemoteRoot>/<ResultsFolder>/<SimulationName>' (or '<ResultsFolder>/<SimulationName>' if
              ResultsFolder is absolute); absolute, so the scripts work from any current directory
    """
    # '/' with an absolute right-hand side keeps only that side, so an absolute ResultsFolder overrides RemoteRoot
    ResultsFolder = PurePosixPath(Config.RemoteRoot) / Config.ResultsFolder
    return f'{ResultsFolder}/{Config.SimulationName}'


def fill_run_config_templates(Config, OutputFolder, MitgcmResultsFolder):
    """
    Fill the !placeholder! tokens of the calendar, forcing and output files (run_config/data.cal, data.exf,
    data.diagnostics, data.mnc) and of the postprocessing scripts (postprocessing/*.py).
    Inputs:
      Config (ConfigObject)     - run settings (dates, time step, exf_albedo, cdrag_1..3)
      OutputFolder (str)        - simulation folder
      MitgcmResultsFolder (str) - absolute results folder on the remote computer (see get_mitgcm_results_folder),
                                  used by the postprocessing scripts; the namelists use the run/results symlink
    Output:
      None - the files are modified in place
    """
    RunConfigFolder = os.path.join(OutputFolder, 'run_config')

    # Calendar (data.cal)
    modify_arguments('!reference_date!', Config.ReferenceDate, os.path.join(RunConfigFolder, 'data.cal'))

    # External forcing (data.exf): start of the forcing files, albedo and wind drag coefficients
    ExfPath = os.path.join(RunConfigFolder, 'data.exf')
    for Token, Value in [('start_date', Config.StartDate), ('exf_albedo', Config.exf_albedo),
                         ('cdrag_1', Config.cdrag_1), ('cdrag_2', Config.cdrag_2), ('cdrag_3', Config.cdrag_3)]:
        modify_arguments(f'!{Token}!', Value, ExfPath)

    # Results folders, through the short run/results symlink: diagnostics are kept, mnc outputs go to a folder meant
    # to be deleted
    modify_arguments('!results_folder!', f'{RESULTS_LINK}/outputs', os.path.join(RunConfigFolder, 'data.diagnostics'))
    modify_arguments('!results_folder!', f'{RESULTS_LINK}/to_delete', os.path.join(RunConfigFolder, 'data.mnc'))

    # Postprocessing scripts run next to MITgcm (reference date in MITgcm's 'YYYY-MM-DD 0:0:0' format)
    ReferenceDate = datetime.strptime(Config.ReferenceDate, '%Y%m%d')
    FormattedRefDate = f'{ReferenceDate.year}-{ReferenceDate.month:02d}-{ReferenceDate.day:02d} 0:0:0'
    for Script in glob.glob(os.path.join(OutputFolder, 'postprocessing/*.py')):
        modify_arguments('!formatted_ref_date!', FormattedRefDate, Script)
        modify_arguments('!time_step!', Config.TimeStep, Script)
        modify_arguments('!results_folder!', f'{MitgcmResultsFolder}/outputs', Script)


def write_data_config_files(DataConfigPath, InitialTemperature, InitialSalt, StartTimeInSecond, EndTimeInSecond,
                            PickupNumber, DzGrid, Config):
    """
    Fill the placeholders of the MITgcm 'data' file (run parameters, initial conditions, vertical grid).
    Inputs:
      DataConfigPath (str)           - copied 'data' file to modify
      InitialTemperature (np.ndarray) - initial temperature profile, same shape as DzGrid
      InitialSalt (np.ndarray)       - initial salinity profile, same shape as DzGrid
      StartTimeInSecond (float)      - start of the simulation, in seconds from the reference date
      EndTimeInSecond (float)        - end of the simulation, in seconds from the reference date
      PickupNumber (str)             - number of the pickup file to restart from ('' if not restarting)
      DzGrid (np.ndarray)            - thickness of each vertical layer [m]
      Config (ConfigObject)          - run settings (grid resolution, time step, viscosities, diffusivities, drag)
    Output:
      None - the file is modified in place
    """
    Replacements = {
        '!initial_temperature!': InitialTemperature,
        '!initial_salt!': InitialSalt,
        '!start_time!': StartTimeInSecond,
        '!end_time!': EndTimeInSecond,
        '!pickup_number!': PickupNumber,
        '!dz_grid!': DzGrid,
        '!grid_resolution!': Config.GridResolution,
        '!time_step!': Config.TimeStep,
        '!viscAz!': Config.viscAz,
        '!diffKzT!': Config.diffKzT,
        '!viscC2smag!': Config.viscC2smag,
        '!viscAhGrid!': Config.viscAhGrid,
        '!diffKhT!': Config.diffKhT,
        '!bottomDragQuadratic!': Config.bottomDragQuadratic,
        '!monitor_freq!': Config.Watchdog['MonitorFreq'],  # statistics in STDOUT.0000, read by watchdog.sh
    }
    for Token, Value in Replacements.items():
        modify_arguments(Token, Value, DataConfigPath)


def write_size_config_files(SizeConfigPath, Px, Py, Nx, Ny, Nr, sNx, sNy):
    """
    Fill the placeholders of MITgcm's code/SIZE.h (domain decomposition).
    Inputs:
      SizeConfigPath (str) - copied SIZE.h file to modify
      Px, Py (int)         - number of processes along x and y
      Nx, Ny (int)         - number of grid cells along x and y
      Nr (int)             - number of vertical layers
      sNx, sNy (int)       - size of one tile along x and y (Nx / Px, Ny / Py)
    Output:
      None - the file is modified in place
    """
    Replacements = {'!Px!': Px, '!Py!': Py, '!Nx!': Nx, '!Ny!': Ny, '!Nr!': Nr, '!sNx!': sNx, '!sNy!': sNy}
    for Token, Value in Replacements.items():
        modify_arguments(Token, Value, SizeConfigPath)


def write_secchi(SwfracPath, SecchiDepths):
    """
    Write the Secchi depths into the Fortran file code/swfrac.F (shortwave penetration).
    Inputs:
      SwfracPath (str)      - copied swfrac.F file to modify
      SecchiDepths (list)   - Secchi depths [m], one per period/value (the list length sets the array size)
    Output:
      None - the file is modified in place
    """
    Declaration = f'_RL secchiDepths({len(SecchiDepths)})'
    # One Fortran DATA statement, continued over several lines ('&' in column 6 = fixed-form continuation)
    Values = ',\n     &                    '.join(f'{Depth} _d 0' for Depth in SecchiDepths)
    Data = f'DATA secchiDepths / {Values} /'

    modify_arguments('!depths!', Declaration, SwfracPath)
    modify_arguments('!secchi!', Data, SwfracPath)


def write_exch2_config(OutputFolder, Config):
    """
    Configure the exch2 package, which lets MITgcm skip the tiles that only contain land.
    Reads the list of land tiles written by grid_and_bathy/check_core_allocation.ipynb
    (file land_cores_Px{Px}_Py{Py}.txt in the grid folder), fills run_config/data.exch2, and returns the
    reduced decomposition: all remaining cores laid out in a single row.
    Doc: https://mitgcm.readthedocs.io/en/latest/phys_pkgs/exch2.html
    Inputs:
      OutputFolder (str)    - simulation folder (contains run_config/data.exch2)
      Config (ConfigObject) - run settings (Px, Py, Nx, Ny and the grid folder)
    Output:
      (tuple[int, int]) - (Px, Py) to write in SIZE.h: Px = Px * Py - number of land tiles, Py = 1
    """
    # File format: line 1 = number of land tiles, line 2 = comma-separated list of their indices
    LandCoresPath = os.path.join(Config.Paths.GridFolderPath, f'land_cores_Px{Config.Px}_Py{Config.Py}.txt')
    with open(LandCoresPath, 'r') as File:
        NbBlankCores, BlankList = File.read().splitlines()
    Values = [Value.strip() for Value in BlankList.split(',') if Value.strip()]

    # Rebuild the list with at most 40 values per line (readable Fortran namelist)
    BlankListFormatted = '\n'.join(','.join(Values[i:i + 40]) + ',' for i in range(0, len(Values), 40))

    Exch2ConfigPath = os.path.join(OutputFolder, 'run_config/data.exch2')
    modify_arguments('!Nx!', Config.Nx, Exch2ConfigPath)
    modify_arguments('!Ny!', Config.Ny, Exch2ConfigPath)
    modify_arguments('!blank_list!', BlankListFormatted, Exch2ConfigPath)

    return Config.Px * Config.Py - int(NbBlankCores), 1
