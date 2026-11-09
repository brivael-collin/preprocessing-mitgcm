import json
import os

import numpy as np
import xarray as xr

from lib.utils.http import fetch_and_save

# CTD profiles from Datalakes (Eawag), e.g. the monthly Canton Zug monitoring at the deepest point of Lake Zug
# (dataset 1325): one JSON file holds every profile, as fields [depth, time]


def download_ctd_datalakes(FileId, FolderPath):
    """
    Download a Datalakes CTD file (all profiles of a dataset) and save it as ctd_<FileId>.json.
    Skips the download if the file already exists.
    Inputs:
      FileId (int)     - Datalakes file id (e.g. 2893450 for the Canton Zug CTD monitoring of Lake Zug)
      FolderPath (str) - folder where the file is saved (created if missing)
    Output:
      FilePath (str) - path of the saved json file
    """
    os.makedirs(FolderPath, exist_ok=True)
    FilePath = os.path.join(FolderPath, f'ctd_{FileId}.json')

    # Download only if missing; fetch_and_save returns an error message instead of raising
    Status = fetch_and_save(f'https://api.datalakes-eawag.ch/download/{FileId}', FilePath)
    if Status.startswith('failed'):
        raise RuntimeError(Status)
    print(f'Datalakes CTD file {Status}: {FilePath}')

    return FilePath


def parse_ctd_datalakes(FilePath):
    """
    Read a Datalakes CTD json file into a dataset of temperature and salinity.
    Input:
      FilePath (str) - json file written by download_ctd_datalakes, with keys 'x' (time, s since 1970),
                       'y' (depth [m], positive downwards), 'z' (temperature [degC]) and 'z5' (salinity [PSU])
    Output:
      (xr.Dataset) - variables 'temp' [degC] and 'salt' [PSU], dims (depth, time); missing values are NaN
    """
    with open(FilePath, 'r') as File:
        Data = json.load(File)

    # Times in seconds since 1970 (UTC) -> timezone-naive datetime64
    Times = np.array(Data['x'], dtype='float').astype('datetime64[s]').astype('datetime64[ns]')
    Depths = np.array(Data['y'], dtype='float')

    # dtype float turns the json nulls into NaN
    return xr.Dataset({'temp': (['depth', 'time'], np.array(Data['z'], dtype='float')),
                       'salt': (['depth', 'time'], np.array(Data['z5'], dtype='float'))},
                      coords={'depth': Depths, 'time': Times})
