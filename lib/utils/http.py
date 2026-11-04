"""Downloads over HTTP shared by the weather, river and Datalakes helpers."""
import os

import requests


def try_download(Url):
    """
    Download a url and raise an error if the request fails.
    Input:
      Url (str) - url to request
    Output:
      (requests.Response) - response with status code 200
    """
    Response = requests.get(Url)
    if Response.status_code != 200:
        raise Exception(f"Didn't work, response.status_code = {Response.status_code}, url = {Url}")

    return Response


def fetch_and_save(Url, FilePath):
    """
    Download a url and save the response text in a file. Skips the download if the file already exists.
    Inputs:
      Url (str)      - url to request
      FilePath (str) - file where the response is saved
    Output:
      Status (str) - 'exists' (skipped), 'saved', or an error message starting with 'failed' (not raised)
    """
    # Skip files already downloaded
    if os.path.isfile(FilePath):
        return 'exists'

    Response = requests.get(Url)
    if Response.status_code == 200:
        with open(FilePath, 'w') as File:
            File.write(Response.text)
        return 'saved'
    return f'failed: {Url} -> {Response.text}'
