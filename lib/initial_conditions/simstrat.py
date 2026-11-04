import glob
import json
import os
from datetime import datetime, timedelta

import numpy as np
import requests
import xarray as xr


def download_simstrat_alplakes(LakeName, StartDate, FolderPath, WindowDays=2):
    """
    Download a Simstrat 1D temperature simulation (depth x time) from the Alplakes API around a given date,
    and save it as a json file readable by parse_alplakes_1d_from_directory. Skips the download if the file exists.
    Inputs:
      LakeName (str)       - Alplakes lake name (e.g. 'zug')
      StartDate (datetime) - date around which the profile is needed (simulation start)
      FolderPath (str)     - folder where the json file is saved (created if missing)
      WindowDays (int)     - number of days downloaded before and after StartDate
    Output:
      (str) - path of the saved json file
    """
    # Time window around the start date, in the API format YYYYmmddHHMM
    WindowStart = (StartDate - timedelta(days=WindowDays)).strftime('%Y%m%d%H%M')
    WindowEnd = (StartDate + timedelta(days=WindowDays)).strftime('%Y%m%d%H%M')
    os.makedirs(FolderPath, exist_ok=True)
    FilePath = os.path.join(FolderPath, f'simstrat_{LakeName}_{WindowStart}_{WindowEnd}.json')

    # Do not download again if the file is already there
    if os.path.isfile(FilePath):
        print(f'Simstrat data already exists: {FilePath}')
        return FilePath

    # Request the data and save the raw json
    Url = f'https://alplakes-api.eawag.ch/simulations/1d/depthtime/simstrat/{LakeName}/{WindowStart}/{WindowEnd}'
    Response = requests.get(Url)
    Response.raise_for_status()
    with open(FilePath, 'w') as File:
        File.write(Response.text)
    print(f'Saved Simstrat data to {FilePath}')
    return FilePath


def parse_alplakes_1d_from_directory(FolderPath):
    """
    Read all Alplakes 1D json files of a folder and combine them into one dataset.
    Input:
      FolderPath (str) - folder containing the json files (all must share the same depth axis)
    Output:
      (xr.Dataset) - variable 'temp' [depth, time] with coordinates 'depth' and 'time' (timezone-naive)
    """
    AllTimes, AllDepths, AllTemperatures = [], [], []

    for FilePath in glob.glob(os.path.join(FolderPath, '*.json')):
        with open(FilePath, 'r') as File:
            Data = json.load(File)

        # Times are ISO strings ending with 'Z' (UTC)
        AllTimes.append([datetime.fromisoformat(Time.replace('Z', '+00:00')) for Time in Data['time']])
        AllDepths.append(np.array(Data['depth']['data']))
        AllTemperatures.append(np.array(Data['variables']['T']['data']))

    # All files must have the same depth axis, the first one is used
    if len({len(Depths) for Depths in AllDepths}) != 1:
        raise ValueError('Depth arrays are not consistent across files.')

    # Concatenate the files along time, and drop the timezone
    Times = np.array([Time.replace(tzinfo=None) for Time in np.concatenate(AllTimes)])
    Temperatures = np.hstack(AllTemperatures)

    return xr.Dataset({'temp': (['depth', 'time'], Temperatures)},
                      coords={'time': Times, 'depth': AllDepths[0]})
