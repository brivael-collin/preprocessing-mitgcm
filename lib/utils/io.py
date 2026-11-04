"""File input/output: fill !placeholder! tokens in text files, read json, write and convert MITgcm binaries."""
import glob
import os

import numpy as np
import orjson


def modify_arguments(ParamName, Values, FilePath, Wrap=9):
    """
    Replace a '!placeholder!' token by its value, in place, in a copied (never template) file.
    Inputs:
      ParamName (str)                    - token to replace, including the '!' (e.g. '!time_step!')
      Values (scalar, str or np.ndarray) - replacement. A 1D array is written comma-separated, Wrap values per line;
                                           a 2D array one row per line. NaN values are dropped.
      FilePath (str)                     - file in which every occurrence of ParamName is replaced
      Wrap (int)                         - number of values per line for a 1D array
    Output:
      None - the file is overwritten
    """
    with open(FilePath, 'r') as File:
        Content = File.read()

    if isinstance(Values, np.ndarray):
        # A 1D array is cut in lines of Wrap values, a 2D array is already one line per row
        Rows = [Values[i:i + Wrap] for i in range(0, len(Values), Wrap)] if Values.ndim == 1 else Values
        ValuesString = '\n'.join(','.join(str(Value) for Value in Row if not np.isnan(Value)) for Row in Rows)
    else:
        ValuesString = str(Values)

    with open(FilePath, 'w') as File:
        File.write(Content.replace(ParamName, ValuesString))


def convert_binary_files(FolderPath, InputDatatype, OutputDatatype):
    """
    Convert the data type (e.g. endianness) of every .bin file of a folder, in place.
    Inputs:
      FolderPath (str)                    - folder containing the .bin files
      InputDatatype (str or np.dtype)     - current data type of the files (e.g. '>f8')
      OutputDatatype (str or np.dtype)    - data type to write (e.g. '<f8')
    Output:
      None - the files are overwritten
    """
    for FilePath in glob.glob(os.path.join(FolderPath, '*.bin')):
        # Read with the current type, convert, write back to the same file
        Data = np.fromfile(FilePath, dtype=InputDatatype).astype(OutputDatatype)
        Data.tofile(FilePath)


def write_binary(FilePath, Data):
    """
    Save an array in the binary format read by MITgcm: big-endian float64, dimension order T, Y, X.
    Inputs:
      FilePath (str)       - output .bin file
      Data (xr.DataArray)  - data to save, already in the order (T, Y, X)
    Output:
      None - file written
    """
    Data.to_numpy().astype('>f8').tofile(FilePath)


def load_json(FilePath):
    """
    Read a json file (fast, with orjson).
    Input:
      FilePath (str) - json file
    Output:
      (dict) - file content
    """
    with open(FilePath, 'rb') as File:
        return orjson.loads(File.read())
