"""Download of the weather data (Alplakes API) used as surface forcing."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

from lib.utils.http import fetch_and_save


# Weather variables requested from the Alplakes API
WEATHER_VARIABLES = ['T_2M', 'U', 'V', 'GLOB', 'RELHUM_2M', 'PMSL', 'CLCT', 'PS']


def download_weather_reanalysis(BaseUrl, StartDate, EndDate, Lat0, Long0, Lat1, Long1, FolderPath):
    """
    Download weather reanalysis from the Alplakes API: one json file per day and variable, in parallel.
    Days already downloaded are skipped.
    Inputs:
      BaseUrl (str)            - Alplakes API url of the weather model
      StartDate, EndDate (str) - first and last day, format 'YYYYmmdd'
      Lat0, Long0 (float)      - south-west corner of the requested box [deg]
      Lat1, Long1 (float)      - north-east corner of the requested box [deg]
      FolderPath (str)         - folder where the json files are saved
    Output:
      None - files '{day}_{day}_{variable}.json' saved in FolderPath
    """
    Day = datetime.strptime(StartDate, '%Y%m%d')
    LastDay = datetime.strptime(EndDate, '%Y%m%d')

    with ThreadPoolExecutor(max_workers=8) as Executor:
        Futures = []
        while Day <= LastDay:
            DayString = Day.strftime('%Y%m%d')
            for Variable in WEATHER_VARIABLES:
                Url = f'{BaseUrl}/{DayString}/{DayString}/{Lat0}/{Long0}/{Lat1}/{Long1}?variables={Variable}'
                FilePath = os.path.join(FolderPath, f'{DayString}_{DayString}_{Variable}.json')
                Futures.append(Executor.submit(fetch_and_save, Url, FilePath))
            Day += timedelta(days=1)

        # Wait for all downloads to finish and collect their status
        Statuses = [Future.result() for Future in Futures]

    # One summary line instead of one line per file; only failures are listed individually
    Failed = [Status for Status in Statuses if Status.startswith('failed')]
    print(f'Weather download ({StartDate}-{EndDate}): {Statuses.count("saved")} downloaded, '
          f'{Statuses.count("exists")} already present, {len(Failed)} failed')
    for Message in Failed:
        print(f'  {Message}')


def download_weather_forecast(BaseUrl, StartDate, Lat0, Long0, Lat1, Long1, FolderPath):
    """
    Download a 4-day weather forecast from the Alplakes API: one json file per variable.
    Inputs:
      BaseUrl (str)       - Alplakes API url of the weather model
      StartDate (str)     - forecast start day, format 'YYYYmmdd'
      Lat0, Long0 (float) - south-west corner of the requested box [deg]
      Lat1, Long1 (float) - north-east corner of the requested box [deg]
      FolderPath (str)    - folder where the json files are saved
    Output:
      None - files '{start}_{end}_{variable}.json' saved in FolderPath
    """
    Start = datetime.strptime(StartDate, '%Y%m%d')
    End = Start + timedelta(days=4)  # TO DO: change the time window for different forecasts?

    for Variable in WEATHER_VARIABLES:
        Url = f'{BaseUrl}/{Start:%Y%m%d}/{Lat0}/{Long0}/{Lat1}/{Long1}?variables={Variable}'
        Response = requests.get(Url)

        if Response.status_code == 200:
            FilePath = os.path.join(FolderPath, f'{Start:%Y%m%d}_{End:%Y%m%d}_{Variable}.json')
            with open(FilePath, 'w') as File:
                File.write(Response.text)
            print(f'Saved data to {FilePath}')
        else:
            print(f'Failed to fetch data for {Start} to {End}. Error : {Response.text}. url : {Url}')


def download_weather(Config, Grid):
    """
    Download the missing weather days from the Alplakes API, for the grid area plus a buffer, into
    1-preprocessing-inputs/raw_from_alplakes_api/<lake>. Days already downloaded are skipped.
    Inputs:
      Config (ConfigObject) - run settings (WeatherModelType, WeatherApiBaseUrl, WeatherDownloadBuffer,
                              StartDate, EndDate, Paths.RawWeatherFolder)
      Grid (MitgcmGrid)     - model grid, its LatGrid / LonGrid set the area to download
    Output:
      None - json files written in Config.Paths.RawWeatherFolder
    """
    os.makedirs(Config.Paths.RawWeatherFolder, exist_ok=True)

    # Area to download: bounding box of the grid plus a buffer [degrees]
    Buffer = Config.WeatherDownloadBuffer
    Corners = (Grid.LatGrid.min() - Buffer, Grid.LonGrid.min() - Buffer,
               Grid.LatGrid.max() + Buffer, Grid.LonGrid.max() + Buffer)

    # Reanalysis: one file per day over the run; forecast: a single forecast starting at StartDate
    if Config.WeatherModelType == 'reanalysis':
        download_weather_reanalysis(Config.WeatherApiBaseUrl, Config.StartDate, Config.EndDate,
                                    *Corners, Config.Paths.RawWeatherFolder)
    elif Config.WeatherModelType == 'forecast':
        download_weather_forecast(Config.WeatherApiBaseUrl, Config.StartDate, *Corners, Config.Paths.RawWeatherFolder)
    else:
        raise ValueError(f'Unknown weather model type: {Config.WeatherModelType}')
