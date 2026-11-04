import os
from datetime import datetime

import numpy as np
import xarray as xr

from lib.utils.http import try_download

# Not used by MAIN_preprocessing.ipynb: helpers to get measured profiles from the Datalakes API (Eawag)


def parse_nc_datalakes_from_folder(FolderPath):
    """
    Open all NetCDF files of a folder as one dataset.
    Input:
      FolderPath (str) - folder containing .nc files
    Output:
      (xr.Dataset) - the files combined by coordinates
    """
    NcFiles = [os.path.join(FolderPath, File) for File in os.listdir(FolderPath) if File.endswith('.nc')]
    if not NcFiles:
        raise FileNotFoundError(f'No NetCDF files found in directory {FolderPath}')

    return xr.open_mfdataset(NcFiles, combine='by_coords')


def datalakes_select_from_depth(Dataset, Variable, GivenDepth):
    """
    Select the time series of a variable at the depth closest to a given one.
    Inputs:
      Dataset (xr.Dataset) - dataset with a 'depth' coordinate
      Variable (str)       - name of the variable to select
      GivenDepth (float)   - wanted depth [m]
    Output:
      (xr.DataArray) - the variable at the closest available depth
    """
    ClosestDepth = Dataset.depth.sel(depth=GivenDepth, method='nearest')

    return Dataset[Variable].sel(depth=ClosestDepth)


def datalakes_select_profile(Dataset, Variable, GivenTime):
    """
    Select the vertical profile of a variable at the time closest to a given one.
    Inputs:
      Dataset (xr.Dataset) - dataset with a 'time' coordinate
      Variable (str)       - name of the variable to select
      GivenTime (datetime) - wanted time
    Output:
      (xr.DataArray) - the variable at the closest available time
    """
    ClosestTime = Dataset.time.sel(time=GivenTime, method='nearest')

    return Dataset[Variable].sel(time=ClosestTime)


def download_ids_files_filtered_by_dates(DatasetId, StartDate, EndDate):
    """
    List the files of a Datalakes dataset that start or end inside a date range.
    Inputs:
      DatasetId (int)      - Datalakes dataset id
      StartDate (datetime) - start of the range (timezone-aware, like the API dates)
      EndDate (datetime)   - end of the range
    Output:
      (list[int]) - ids of the matching files
    """
    FilesProperties = try_download(f'https://api.datalakes-eawag.ch/files?datasets_id={DatasetId}').json()

    FileIds = []
    for File in FilesProperties:
        if File['mindatetime'] is None or File['maxdatetime'] is None:
            continue
        MinDate = datetime.fromisoformat(File['mindatetime'].replace('Z', '+00:00'))
        MaxDate = datetime.fromisoformat(File['maxdatetime'].replace('Z', '+00:00'))
        # Keep the file if its first or its last date falls in the range
        if StartDate < MinDate < EndDate or StartDate < MaxDate < EndDate:
            FileIds.append(File['id'])

    return FileIds


def download_data_from_datalakes_file(FileId):
    """
    Download one Datalakes file holding a temperature field (depth x time).
    Input:
      FileId (int) - Datalakes file id
    Output:
      (xr.Dataset) - variable 'temp' [depth, time]; depth is positive downwards
    """
    JsonMeasure = try_download(f'https://api.datalakes-eawag.ch/download/{FileId}').json()

    return xr.Dataset(
        {'temp': (['depth', 'time'], np.array(JsonMeasure['z'], dtype='float'))},
        coords={'time': np.array(JsonMeasure['x'], dtype='datetime64[s]').astype('datetime64[ns]'),
                'depth': -1 * np.array(JsonMeasure['y'], dtype='float')})


def download_data_from_datalakes_dataset(DatasetId, StartDate, EndDate):
    """
    Download and merge all files of a Datalakes dataset inside a date range.
    Inputs:
      DatasetId (int)      - Datalakes dataset id
      StartDate (datetime) - start of the range
      EndDate (datetime)   - end of the range
    Output:
      (xr.Dataset or None) - merged 'temp' [depth, time], None if no file matches
    """
    MergedDataset = None
    for FileId in download_ids_files_filtered_by_dates(DatasetId, StartDate, EndDate):
        FileDataset = download_data_from_datalakes_file(FileId)
        MergedDataset = FileDataset if MergedDataset is None else xr.merge([MergedDataset, FileDataset])

    return MergedDataset


def get_id_file_with_closest_date(DatasetId, Date):
    """
    Find the file of a dataset whose last date is the closest before a given date.
    Inputs:
      DatasetId (int) - Datalakes dataset id
      Date (datetime) - reference date (timezone-naive)
    Output:
      (tuple[datetime, int]) - (last date of the file, file id); (1900-01-01, 0) if none is before Date
    """
    FilesProperties = try_download(f'https://api.datalakes-eawag.ch/files?datasets_id={DatasetId}').json()

    FileId = 0
    FileDate = datetime(1900, 1, 1)
    for File in FilesProperties:
        if File['mindatetime'] is None or File['maxdatetime'] is None:
            continue
        MaxDate = datetime.fromisoformat(File['maxdatetime'].replace('Z', '+00:00')).replace(tzinfo=None)
        # Keep the latest file that ends before Date
        if MaxDate <= Date and Date - MaxDate < Date - FileDate:
            FileId, FileDate = File['id'], MaxDate

    return FileDate, FileId


def download_data_from_idronaut_file(FileId):
    """
    Download one Datalakes file holding an Idronaut temperature profile.
    Input:
      FileId (int) - Datalakes file id
    Output:
      (xr.Dataset) - variable 'temp' [depth]
    """
    JsonMeasure = try_download(f'https://api.datalakes-eawag.ch/download/{FileId}').json()

    return xr.Dataset({'temp': (['depth'], np.array(JsonMeasure['x'], dtype='float'))},
                      coords={'depth': np.array(JsonMeasure['y'], dtype='float')})
