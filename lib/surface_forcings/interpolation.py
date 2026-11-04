"""Interpolation of the raw weather json files to the MITgcm grid, and writing of the surface forcing binaries."""
import glob
import os
import re
import time
from datetime import datetime

import numpy as np
import pandas as pd
import xarray as xr
from scipy.interpolate import griddata
from tqdm import tqdm

from lib.utils.io import load_json, write_binary
from .physics import calculate_specific_humidity, compute_longwave_radiation


def extract_data_from_json(JsonData, JsonPath, DataType):
    """
    Get the data of a variable from an Alplakes json, which stores it at the top level or under 'variables'.
    Inputs:
      JsonData (dict) - content of the json file
      JsonPath (str)  - path of the json file (only used in the error message)
      DataType (str)  - variable name (e.g. 'T_2M')
    Output:
      (np.ndarray) - data of the variable, shape (time, y, x)
    """
    if DataType in JsonData:
        return np.array(JsonData[DataType]['data'])
    if 'variables' in JsonData and DataType in JsonData['variables']:
        return np.array(JsonData['variables'][DataType]['data'])
    raise KeyError(f"Data type '{DataType}' not found in JSON {JsonPath}.")


def select_first_24h(ParsedTimes, Data):
    """
    Keep only the first 24 hours of a time series.
    Inputs:
      ParsedTimes (pd.DatetimeIndex) - sorted times
      Data (np.ndarray)              - data, first axis is time
    Output:
      (tuple) - (times, data) restricted to the first 24 hours
    """
    StartTime = ParsedTimes[0]
    IsValid = (ParsedTimes >= StartTime) & (ParsedTimes < StartTime + pd.Timedelta(hours=24))

    return ParsedTimes[IsValid], Data[IsValid]


def interp_to_grid(JsonFile, DataType, Grid, WeatherModelType=''):
    """
    Interpolate the data of one json file from the weather model grid to the MITgcm grid, for every time.
    Inputs:
      JsonFile (str)           - Alplakes json file
      DataType (str)           - variable name in the file (e.g. 'T_2M')
      Grid (MitgcmGrid)        - MITgcm grid to interpolate to
      WeatherModelType (str)   - 'forecast' keeps all times, otherwise only the first 24 h are kept
    Output:
      (xr.DataArray) - interpolated data with dimensions (T, Y, X), sorted by time
    """
    JsonData = load_json(JsonFile)

    # Times as timezone-naive datetimes
    ParsedTimes = pd.to_datetime(JsonData['time']).tz_localize(None)

    # Coordinates of the weather model points
    Lat, Lon = np.array(JsonData['lat']), np.array(JsonData['lng'])
    RawCoordinates = np.column_stack((Lat.flatten(), Lon.flatten()))

    Data = extract_data_from_json(JsonData, JsonFile, DataType)
    if WeatherModelType != 'forecast':
        ParsedTimes, Data = select_first_24h(ParsedTimes, Data)

    # Linear interpolation of each time step to the MITgcm cells
    InterpolatedData = [
        xr.DataArray(griddata(RawCoordinates, Data[i].flatten(), (Grid.LatGrid, Grid.LonGrid), method='linear'),
                     dims=['Y', 'X'],
                     coords={'X': Grid.X, 'Y': Grid.Y, 'T': Time})
        for i, Time in enumerate(ParsedTimes)
    ]

    return xr.concat(InterpolatedData, dim='T').sortby('T')


def filter_json_files_by_date(JsonFiles, StartDate, EndDate):
    """
    Keep the json files whose period (dates in the file name: '{start}_{end}_{variable}.json') overlaps the
    requested period.
    Inputs:
      JsonFiles (list[str]) - json file paths
      StartDate (str)       - first day, format 'YYYYmmdd'
      EndDate (str)         - last day, format 'YYYYmmdd'
    Output:
      (list[str]) - selected files
    """
    Start = datetime.strptime(StartDate, '%Y%m%d')
    End = datetime.strptime(EndDate, '%Y%m%d')

    def is_within_range(File):
        FileDates = re.findall(r'\d{8}', File)
        FileStart = datetime.strptime(FileDates[0], '%Y%m%d')
        FileEnd = datetime.strptime(FileDates[1], '%Y%m%d')
        return Start <= FileStart <= End and FileEnd >= Start

    return list(filter(is_within_range, JsonFiles))


def interp_concat_json(FolderJsonPath, DataType, StartDate, EndDate, Grid, WeatherModelType=''):
    """
    Interpolate all json files of a variable to the MITgcm grid and join them into one hourly series.
    Inputs:
      FolderJsonPath (str)   - folder containing the json files
      DataType (str)         - variable name (e.g. 'T_2M')
      StartDate, EndDate (str) - period, format 'YYYYmmdd'
      Grid (MitgcmGrid)      - MITgcm grid to interpolate to
      WeatherModelType (str) - 'forecast' or 'reanalysis'
    Output:
      (xr.DataArray) - hourly data with dimensions (T, Y, X), from StartDate to EndDate
    """
    AllJsonFiles = glob.glob(os.path.join(FolderJsonPath, f'*_{DataType}.json'))
    JsonFiles = filter_json_files_by_date(AllJsonFiles, StartDate, EndDate)

    AllData = xr.concat([interp_to_grid(File, DataType, Grid, WeatherModelType) for File in JsonFiles],
                        dim='T').sortby('T')

    # Files overlap in time: keep the first value of each duplicated time
    _, UniqueIndices = np.unique(AllData['T'].values, return_index=True)
    CleanedData = AllData.isel(T=np.sort(UniqueIndices))

    # Interpolate to a regular hourly time axis, so that time is consistent
    HourlyTimes = pd.date_range(start=pd.to_datetime(StartDate, format='%Y%m%d'),
                                end=pd.to_datetime(EndDate, format='%Y%m%d'), freq='h').to_list()

    return CleanedData.interp({'T': HourlyTimes}).transpose('T', 'Y', 'X')


def extract_and_save_surface_forcings(OutputFolderPath, StartDate, EndDate, RawWeatherFolderPath, Grid, ALw,
                                      WeatherModelType=''):
    """
    Extract the surface forcings from the Alplakes json files and save them as MITgcm binary files:
    u10, v10, swdown, atemp, apressure, relhum, clct, aqh (computed) and lwdown (computed).
    Inputs:
      OutputFolderPath (str)     - folder of the binary files (created if missing)
      StartDate, EndDate (str)   - period, format 'YYYYmmdd' (e.g. '20190301')
      RawWeatherFolderPath (str) - folder containing the json files
      Grid (MitgcmGrid)          - MITgcm grid, created with get_grid from grid_and_bathy
      ALw (float)                - longwave calibration parameter
      WeatherModelType (str)     - 'reanalysis' or 'forecast'
    Output:
      None - .bin files written in OutputFolderPath
    """
    os.makedirs(OutputFolderPath, exist_ok=True)
    StartTime = time.time()

    # One bar for the whole section: 7 interpolated variables + 2 computed ones
    Bar = tqdm(total=9, bar_format='{l_bar}{bar} {n_fmt}/{total_fmt} [{elapsed}]')

    def process_variable(VariableName, OutputName):
        """Interpolate one weather variable to the grid, save it as OutputName.bin and return it."""
        Bar.set_description_str(f'Interpolating {VariableName} -> {OutputName}.bin')
        Data = interp_concat_json(RawWeatherFolderPath, VariableName, StartDate, EndDate, Grid, WeatherModelType)
        write_binary(os.path.join(OutputFolderPath, f'{OutputName}.bin'), Data)
        Bar.update(1)
        return Data

    # Variables used as they are
    process_variable('U', 'u10')
    process_variable('V', 'v10')
    process_variable('GLOB', 'swdown')

    # Variables also needed to compute humidity and longwave radiation
    ATemp = process_variable('T_2M', 'atemp')
    APress = process_variable('PS', 'apressure')
    RelHum = process_variable('RELHUM_2M', 'relhum')
    CloudCover = process_variable('CLCT', 'clct')

    Bar.set_description_str('Computing specific humidity -> aqh.bin')
    write_binary(os.path.join(OutputFolderPath, 'aqh.bin'), calculate_specific_humidity(ATemp, RelHum, APress))
    Bar.update(1)

    Bar.set_description_str('Computing longwave radiation -> lwdown.bin')
    write_binary(os.path.join(OutputFolderPath, 'lwdown.bin'),
                 compute_longwave_radiation(ATemp, RelHum, CloudCover, ALw))
    Bar.update(1)
    Bar.set_description_str('Finished')
    Bar.close()

    # Short conclusion: what was written, for which period, on which grid, and how long it took
    Size = ATemp.shape
    print(f'Surface forcings done in {time.time() - StartTime:.0f} s: 9 binary files written to {OutputFolderPath}\n'
          f'  period {StartDate}-{EndDate} ({Size[0]} hourly steps), grid {Size[2]} x {Size[1]} (X x Y), '
          f'{WeatherModelType or "reanalysis"} data')
