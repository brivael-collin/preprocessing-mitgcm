# Adapted from https://github.com/leroquan/mitgcm_toolbox/blob/master/PythonScripts/generate_river_data.py

import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
import xarray as xr

from lib.grid_and_bathy import convert_point_coord_to_mitgcm_coord, get_dz_grid
from lib.utils.http import try_download
from lib.utils.io import modify_arguments

BOUNDARY_DIRECTIONS = ['north', 'south', 'east', 'west']

# Per boundary: MITgcm variable name of the cell index, velocity component, and which indices it is read from
# (north/south boundaries are indexed by x, east/west boundaries by y)
BOUNDARY_SETTINGS = {
    'north': {'ObcsIndex': 'OB_Jnorth', 'Velocity': 'v', 'IndexedBy': 'x_idx'},
    'south': {'ObcsIndex': 'OB_Jsouth', 'Velocity': 'v', 'IndexedBy': 'x_idx'},
    'east': {'ObcsIndex': 'OB_Ieast', 'Velocity': 'u', 'IndexedBy': 'y_idx'},
    'west': {'ObcsIndex': 'OB_Iwest', 'Velocity': 'u', 'IndexedBy': 'y_idx'},
}


def build_river_config(Config, OutputDir, SaveFiles=True):
    """
    Locate each river mouth on the MITgcm grid and write the open boundary (obcs) settings.
    Inputs:
      Config (ConfigObject) - run settings, with the list of rivers (Config.Rivers)
      OutputDir (str)       - folder containing data.obcs, where river_dicts.json is also written
      SaveFiles (bool)      - False to only compute and return the results
    Output:
      (tuple) - (RiverDicts, ObsIndicesString):
                RiverDicts (list[dict]) - for each river: name, bafu_id, variable names, grid indices x_idx / y_idx,
                                          boundary_direction, in_or_out and depth
                ObsIndicesString (str)  - OB_* lines written in data.obcs (placeholder '!set_obs_indices!')
    """
    RiverDicts = []
    for River in Config.Rivers:
        # River mouth in the model frame, then the index of its cell
        XCoord, YCoord = convert_point_coord_to_mitgcm_coord(River.CoordinatesLakePoint[0],
                                                             River.CoordinatesLakePoint[1], '2056', Config)
        RiverDicts.append({
            'name': River.Name,
            'bafu_id': River.BafuId,
            'discharge_variable_name': River.DischargeVariableName,
            'temperature_variable_name': River.TemperatureVariableName,
            'x_idx': int(XCoord / Config.GridResolution),
            'y_idx': int(YCoord / Config.GridResolution),
            'boundary_direction': River.Direction,
            'in_or_out': River.InOrOut,
            'depth': River.RiverDepth,
        })

    # Open boundary settings of data.obcs, boundary by boundary (MITgcm indices start at 1)
    ObsIndicesString = ''
    ObsPathString = ''
    for Direction in BOUNDARY_DIRECTIONS:
        Settings = BOUNDARY_SETTINGS[Direction]
        for RiverDict in RiverDicts:
            if RiverDict['boundary_direction'] != Direction:
                continue
            X, Y = RiverDict['x_idx'] + 1, RiverDict['y_idx'] + 1
            # North/south boundaries: OB_J(x) = y. East/west boundaries: OB_I(y) = x.
            Index, Value = (X, Y) if Settings['IndexedBy'] == 'x_idx' else (Y, X)
            ObsIndicesString += f' {Settings["ObcsIndex"]}({Index}) = {Value}\n'

            Initial = Direction[0].upper()
            ObsPathString += (f"OB{Initial}{Settings['Velocity']}File = "
                              f"'../binary_data/bc_{Direction}_{Settings['Velocity']}.bin'\n")
            # Temperature of the inflowing water
            if RiverDict['in_or_out'] == 'in':
                ObsPathString += f"OB{Initial}TFile = '../binary_data/bc_{Direction}_temp.bin'\n"

    if SaveFiles:
        # Fill data.obcs (without the last line break) and save the river list for build_river_binaries
        ObcsPath = os.path.join(OutputDir, 'data.obcs')
        modify_arguments('!set_obs_indices!', ObsIndicesString[:-1], ObcsPath)
        modify_arguments('!set_obs_path!', ObsPathString[:-1], ObcsPath)

        with open(os.path.join(OutputDir, 'river_dicts.json'), 'w') as File:
            json.dump(RiverDicts, File, indent=2)

    return RiverDicts, ObsIndicesString


def cell_flow(MaxH, H1, H2, TotalFlow):
    """
    Flow through one cell, from the logarithmic law of turbulent boundary layers, as per
    'Modelling Aquatic Ecosystems' by Reichert, Mieleitner and Schuwirth.
    Inputs:
      MaxH (float)      - total depth of the river mouth [m]
      H1, H2 (float)    - depth of the top and the bottom of the cell [m]
      TotalFlow (float) - discharge of the river [m3/s]
    Output:
      (float) - flow through the cell [m3/s]
    """
    Kappa = 0.4
    Slope = 0.01
    UStar = np.sqrt(9.8 * MaxH * Slope)

    Flow = TotalFlow * (H2 / MaxH) + (UStar / Kappa) * H2 * np.log(H2 / MaxH)
    # The top cell (H1 = 0) has nothing to subtract
    if H1 > 0:
        Flow -= TotalFlow * (H1 / MaxH) + (UStar / Kappa) * H1 * np.log(H1 / MaxH)

    return Flow


def vector_flow(TotalFlow, H):
    """
    Velocity profile of the river over the depth, with the zeroth value corresponding to the bottom cell.
    Inputs:
      TotalFlow (float) - discharge of the river [m3/s]
      H (np.ndarray)    - depth of the cell interfaces, starting at 0 at the surface [m]
    Output:
      (np.ndarray) - flow per metre of depth in each cell [m2/s], ordered from the bottom to the top
    """
    NbCells = len(H) - 1
    Flows = np.zeros(NbCells)
    for i in range(NbCells):
        Flows[NbCells - i - 1] = cell_flow(H[NbCells], H[i], H[i + 1], TotalFlow) / (H[i + 1] - H[i])

    return Flows


def parse_river_json(JsonData):
    """
    Convert a BAFU json (time series of one variable) to a dataset.
    Input:
      JsonData (dict) - json with 'time' (ISO strings) and 'variable'['data']
    Output:
      (xr.Dataset) - variable 'data' along the coordinate 'time' (timezone-naive)
    """
    Times = [datetime.fromisoformat(Time.replace('Z', '+00:00')).replace(tzinfo=None) for Time in JsonData['time']]
    Values = np.array(JsonData['variable']['data'])

    return xr.Dataset({'data': (['time'], Values)}, coords={'time': Times})


def download_river_variable(Config, BafuId, VariableName, DateList):
    """
    Download a measured BAFU time series and interpolate it to the simulation times.
    Inputs:
      Config (ConfigObject)     - run settings (start and end date)
      BafuId (int)              - id of the BAFU station
      VariableName (str)        - BAFU variable (discharge or temperature)
      DateList (pd.DatetimeIndex) - times to interpolate to
    Output:
      (xr.Dataset) - variable 'data' along 'time', at the times of DateList
    """
    Url = (f'https://alplakes-internal-api.eawag.ch/bafu/hydrodata/measured/{BafuId}/{VariableName}/'
           f'{Config.StartDate}/{Config.EndDate}/?resample=hourly')

    return parse_river_json(try_download(Url).json()).interp(time=DateList, method='linear')


def get_formatted_velocities(Config, RiverConfig, DateList, ZGrid, IdxMaxZRiver):
    """
    Velocity profile of a river at each time step.
    Inputs:
      Config (ConfigObject)       - run settings
      RiverConfig (pd.Series)     - one river of river_dicts.json
      DateList (pd.DatetimeIndex) - simulation times (hourly)
      ZGrid (np.ndarray)          - depth of the bottom of each layer [m]
      IdxMaxZRiver (int)          - index of the deepest layer receiving the river
    Output:
      (list[np.ndarray]) - for each time, the velocity in each layer of the river [m/s], from the bottom up
    """
    Discharge = download_river_variable(Config, RiverConfig['bafu_id'], RiverConfig['discharge_variable_name'],
                                        DateList)
    DepthProfile = np.insert(ZGrid[0:(IdxMaxZRiver + 1)], 0, 0)

    # Flow per layer divided by the cell width gives the velocity
    return [vector_flow(Discharge.isel(time=i).data.values, DepthProfile) / Config.GridResolution
            for i in range(len(DateList))]


def get_formatted_temperature(Config, RiverConfig, DateList):
    """
    Water temperature of a river at each time step.
    Inputs:
      Config (ConfigObject)       - run settings
      RiverConfig (pd.Series)     - one river of river_dicts.json
      DateList (pd.DatetimeIndex) - simulation times (hourly)
    Output:
      (np.ndarray) - temperature at each time [deg C]
    """
    Temperature = download_river_variable(Config, RiverConfig['bafu_id'], RiverConfig['temperature_variable_name'],
                                          DateList)

    return Temperature.data.values


def get_boundary_direction_factor(Direction, InOrOut):
    """
    Sign of the boundary velocity: positive towards north or east, so a river flowing into the lake from the
    north or east boundary, or out of it through the south or west boundary, has a negative velocity.
    Inputs:
      Direction (str) - boundary: 'north', 'south', 'east' or 'west'
      InOrOut (str)   - 'in' for an inflow, 'out' for an outflow
    Output:
      (int) - 1 or -1
    """
    IsNegative = (Direction, InOrOut) in [('south', 'out'), ('north', 'in'), ('west', 'out'), ('east', 'in')]

    return -1 if IsNegative else 1


def define_direction_specific_variables(Config, Direction):
    """
    Variables depending on the boundary direction.
    Inputs:
      Config (ConfigObject) - run settings (Nx, Ny)
      Direction (str)       - boundary: 'north', 'south', 'east' or 'west'
    Output:
      (tuple) - (velocity component 'u' or 'v', name of the river index along the boundary in river_dicts.json,
                 number of cells along the boundary)
    """
    if Direction in ('south', 'north'):
        return 'v', 'x_idx', Config.Nx
    return 'u', 'y_idx', Config.Ny


def write_river_binaries(BinaryDataFolder, Direction, VelocityVariable, DateList, DzGrid, BoundaryLength,
                         BoundaryRivers):
    """
    Append the velocity and temperature of all rivers of one boundary to the binary boundary condition files
    bc_{Direction}_{u or v}.bin and bc_{Direction}_temp.bin (big-endian float64, one (z, boundary) slice per time).
    Inputs:
      BinaryDataFolder (str)      - folder of the binary files
      Direction (str)             - boundary: 'north', 'south', 'east' or 'west'
      VelocityVariable (str)      - 'u' or 'v'
      DateList (pd.DatetimeIndex) - simulation times
      DzGrid (np.ndarray)         - thickness of each vertical layer [m]
      BoundaryLength (int)        - number of cells along the boundary
      BoundaryRivers (list[dict]) - for each river: 'horizontal_idx', 'max_z_idx', 'velocity' and 'temperature'
                                    (one value or profile per time)
    Output:
      None - files appended
    """
    VelocityPath = f'{BinaryDataFolder}/bc_{Direction}_{VelocityVariable}.bin'
    TemperaturePath = f'{BinaryDataFolder}/bc_{Direction}_temp.bin'

    with open(VelocityPath, 'ab') as VelocityFile, open(TemperaturePath, 'ab') as TemperatureFile:
        for i in range(len(DateList)):
            Velocities = np.zeros((len(DzGrid), BoundaryLength), dtype='>f8')
            Temperatures = np.zeros((len(DzGrid), BoundaryLength), dtype='>f8')
            # Each river fills the layers from the surface to its depth, in the cell(s) of its mouth
            for BoundaryRiver in BoundaryRivers:
                Layers = slice(0, BoundaryRiver['max_z_idx'] + 1)
                Velocities[Layers, BoundaryRiver['horizontal_idx']] = BoundaryRiver['velocity'][i]
                Temperatures[Layers, BoundaryRiver['horizontal_idx']] = BoundaryRiver['temperature'][i]

            Velocities.tofile(VelocityFile)
            Temperatures.tofile(TemperatureFile)


def build_river_binaries(Config, OutputDir):
    """
    Download the river discharge and temperature (BAFU) and write the open boundary condition binary files.
    Needs river_dicts.json (written by build_river_config) and dz.csv in the grid folder.
    Inputs:
      Config (ConfigObject) - run settings
      OutputDir (str)       - folder where the binary files are written
    Output:
      None - bc_{north,south,east,west}_{u or v}.bin and bc_*_temp.bin written for the boundaries with rivers
    """
    RiverConfig = pd.read_json(os.path.join(Config.Paths.GridFolderPath, 'river_dicts.json'))
    DateList = pd.date_range(Config.StartDate, Config.EndDate, freq='1h')

    DzGrid = get_dz_grid(os.path.join(Config.Paths.GridFolderPath, 'dz.csv')).flatten()
    ZGrid = np.cumsum(DzGrid)

    for Direction in BOUNDARY_DIRECTIONS:
        VelocityVariable, IndexName, BoundaryLength = define_direction_specific_variables(Config, Direction)

        BoundaryRivers = []
        for _, River in RiverConfig[RiverConfig['boundary_direction'] == Direction].iterrows():
            # Deepest layer reached by the river
            IdxMaxZRiver = np.abs(ZGrid - River['depth']).argmin()
            Velocity = get_formatted_velocities(Config, River, DateList, ZGrid, IdxMaxZRiver)
            Factor = get_boundary_direction_factor(Direction, River['in_or_out'])

            BoundaryRivers.append({'horizontal_idx': River[IndexName],
                                   'max_z_idx': IdxMaxZRiver,
                                   'velocity': Factor * np.array(Velocity),
                                   'temperature': get_formatted_temperature(Config, River, DateList)})

        if BoundaryRivers:
            write_river_binaries(OutputDir, Direction, VelocityVariable, DateList, DzGrid, BoundaryLength,
                                 BoundaryRivers)
