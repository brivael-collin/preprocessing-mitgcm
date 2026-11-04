import os

import numpy as np
import pandas as pd
from pyproj import Transformer


class MitgcmGrid:
    """
    MITgcm horizontal grid, loaded from .npy files.
    Attributes (all np.ndarray, empty until load_from_path is called):
      X, Y (1D)            - cell coordinates along the model x and y axes [m]
      LatGrid, LonGrid (2D) - latitude and longitude of each cell [deg], shape (Ny, Nx)
    """

    def __init__(self):
        self.X = np.array([])
        self.Y = np.array([])
        self.LatGrid = np.array([])
        self.LonGrid = np.array([])

    def load_from_path(self, GridFolderPath):
        """
        Load the grid from a folder containing x.npy, y.npy, lat_grid.npy and lon_grid.npy.
        Input:
          GridFolderPath (str) - folder containing the grid files
        Output:
          None - the attributes are filled. Raises FileNotFoundError if a file is missing.
        """
        try:
            self.X = np.load(os.path.join(GridFolderPath, 'x.npy'))
            self.Y = np.load(os.path.join(GridFolderPath, 'y.npy'))
            self.LatGrid = np.load(os.path.join(GridFolderPath, 'lat_grid.npy'))
            self.LonGrid = np.load(os.path.join(GridFolderPath, 'lon_grid.npy'))
        except FileNotFoundError as Error:
            raise FileNotFoundError(f'Missing grid file: {Error.filename}') from Error


def get_grid(GridFolderPath):
    """
    Create a MitgcmGrid and load it from files.
    Input:
      GridFolderPath (str) - folder containing the grid .npy files
    Output:
      (MitgcmGrid) - the loaded grid
    """
    Grid = MitgcmGrid()
    Grid.load_from_path(GridFolderPath)

    return Grid


def create_regular_grid(Nx, Ny, XResolution, YResolution):
    """
    Create a regular grid starting at the origin (0, 0).
    Inputs:
      Nx, Ny (int)                     - number of cells along x and y
      XResolution, YResolution (float) - cell size along x and y [m]
    Output:
      (tuple of np.ndarray) - (X, Y, XGrid, YGrid): 1D coordinates along each axis, and their 2D meshgrid
    """
    X = np.arange(0, Nx * XResolution, XResolution)
    Y = np.arange(0, Ny * YResolution, YResolution)
    XGrid, YGrid = np.meshgrid(X, Y)

    return X, Y, XGrid, YGrid


def translate_grid(X, Y, Dx, Dy):
    """
    Translate coordinates.
    Inputs:
      X, Y (np.ndarray) - coordinates to translate
      Dx, Dy (float)    - shift along x and y
    Output:
      (tuple of np.ndarray) - translated (X, Y)
    """
    return X + Dx, Y + Dy


def get_grid_angle(X0, Y0, X1, Y1):
    """
    Angle between the positive x-axis and the segment from point (X0, Y0) to point (X1, Y1).
    Inputs:
      X0, Y0 (float) - first point
      X1, Y1 (float) - second point
    Output:
      (float) - angle [rad]
    """
    return np.arctan2(Y1 - Y0, X1 - X0)


def rotate_grid(X, Y, X0, Y0, RotationAngle):
    """
    Rotate coordinates around a point.
    Inputs:
      X, Y (np.ndarray)    - coordinates to rotate
      X0, Y0 (float)       - centre of the rotation
      RotationAngle (float) - counter-clockwise angle [rad]
    Output:
      (tuple of np.ndarray) - rotated (X, Y)
    """
    # Rotate around the origin, so move the centre there and back
    XCentered, YCentered = translate_grid(X, Y, -X0, -Y0)

    XRotated = np.cos(RotationAngle) * XCentered - np.sin(RotationAngle) * YCentered
    YRotated = np.sin(RotationAngle) * XCentered + np.cos(RotationAngle) * YCentered

    return translate_grid(XRotated, YRotated, X0, Y0)


def save_grid(FolderPathOut, X, Y, XRotated, YRotated, LatGrid, LonGrid, CrsIni='21781'):
    """
    Save the grid arrays as .npy files (created folder if missing).
    Inputs:
      FolderPathOut (str)            - output folder
      X, Y (np.ndarray)              - 1D model coordinates [m]
      XRotated, YRotated (np.ndarray) - 2D coordinates of the cells in the initial projection
      LatGrid, LonGrid (np.ndarray)  - 2D latitude and longitude of the cells [deg]
      CrsIni (str)                   - EPSG code of the initial projection, used in the file names
    Output:
      None - files x.npy, y.npy, x_epsg{CrsIni}_grid.npy, y_epsg{CrsIni}_grid.npy, lat_grid.npy, lon_grid.npy
    """
    os.makedirs(FolderPathOut, exist_ok=True)

    Arrays = {'x': X, 'y': Y, f'x_epsg{CrsIni}_grid': XRotated, f'y_epsg{CrsIni}_grid': YRotated,
              'lat_grid': LatGrid, 'lon_grid': LonGrid}
    for Name, Array in Arrays.items():
        np.save(os.path.join(FolderPathOut, f'{Name}.npy'), Array)


def build_grid(Nx, Ny, XResolution, YResolution, X0, Y0, RotationAngle, CrsIni='21781', CrsTarget='4326'):
    """
    Build a rotated regular grid and its latitude/longitude.
    Inputs:
      Nx, Ny (int)                     - number of cells along x and y
      XResolution, YResolution (float) - cell size along x and y [m]
      X0, Y0 (float)                   - origin of the grid, in the initial projection
      RotationAngle (float)            - rotation of the grid around its origin [rad]
      CrsIni (str)                     - EPSG code of the initial projection (X0, Y0)
      CrsTarget (str)                  - EPSG code of the output lat/lon projection
    Output:
      (tuple of np.ndarray) - (X, Y, XRotated, YRotated, LatGrid, LonGrid): 1D model coordinates, 2D rotated
                              coordinates in the initial projection, 2D latitude and longitude
    """
    X, Y, _, _ = create_regular_grid(Nx, Ny, XResolution, YResolution)

    # Place the grid at its origin, then rotate it around this origin
    XIni, YIni = translate_grid(X, Y, X0, Y0)
    XGrid, YGrid = np.meshgrid(XIni, YIni)
    XRotated, YRotated = rotate_grid(XGrid, YGrid, X0, Y0, RotationAngle)

    # Convert to latitude / longitude
    CoordConverter = Transformer.from_crs(f'EPSG:{CrsIni}', f'EPSG:{CrsTarget}', always_xy=True)
    LonGrid, LatGrid = CoordConverter.transform(XRotated, YRotated)

    return X, Y, XRotated, YRotated, LatGrid, LonGrid


def build_and_save_mitgcm_grid(FolderPathOut, Nx, Ny, GridResolution, X0, Y0, RotationAngle,
                               CrsIni='21781', CrsTarget='4326'):
    """
    Build a square-cell grid and save it (see build_grid and save_grid).
    Inputs:
      FolderPathOut (str)   - output folder
      Nx, Ny (int)          - number of cells along x and y
      GridResolution (float) - cell size [m]
      X0, Y0 (float)        - origin of the grid, in the initial projection
      RotationAngle (float) - rotation of the grid around its origin [rad]
      CrsIni, CrsTarget (str) - EPSG codes of the initial and target projections
    Output:
      None - grid files saved in FolderPathOut
    """
    X, Y, XRotated, YRotated, LatGrid, LonGrid = build_grid(Nx, Ny, GridResolution, GridResolution,
                                                            X0, Y0, RotationAngle, CrsIni, CrsTarget)
    save_grid(FolderPathOut, X, Y, XRotated, YRotated, LatGrid, LonGrid)


def get_dz_grid(DzGridFilePath):
    """
    Read the thickness of the vertical layers.
    Input:
      DzGridFilePath (str) - csv file without header (dz.csv)
    Output:
      (np.ndarray) - layer thicknesses [m], NaN for unused layers
    """
    return pd.read_csv(DzGridFilePath, header=None).to_numpy()


def convert_point_coord_to_mitgcm_coord(XPoint, YPoint, PointEpsgProjection, Config):
    """
    Convert point coordinates into the MITgcm model frame (origin at the grid corner, axes rotated with the grid).
    Inputs:
      XPoint, YPoint (float or np.ndarray) - coordinates of the point(s)
      PointEpsgProjection (str)            - EPSG code of the point coordinates
      Config (ConfigObject)                - run settings (grid origin, projection, rotation, resolution)
    Output:
      (tuple) - (X, Y) of the point(s) in the model frame [m]
    """
    CrsTarget = '2056'

    # Grid origin in the target projection, moved to the centre of the first cell
    OriginConverter = Transformer.from_crs(f'EPSG:{Config.EpsgProjection}', f'EPSG:{CrsTarget}', always_xy=True)
    X0, Y0 = OriginConverter.transform(Config.X0, Config.Y0)
    X0, Y0 = X0 + Config.GridResolution / 2, Y0 + Config.GridResolution / 2
    RotationAngle = np.deg2rad(Config.Rotation)

    # Point in the target projection
    PointConverter = Transformer.from_crs(f'EPSG:{PointEpsgProjection}', f'EPSG:{CrsTarget}', always_xy=True)
    X, Y = PointConverter.transform(XPoint, YPoint)

    # Move the origin to (0, 0) and undo the grid rotation
    XTranslated, YTranslated = translate_grid(X, Y, -X0, -Y0)
    XMitgcm, YMitgcm = rotate_grid(XTranslated, YTranslated, 0, 0, -RotationAngle)

    return XMitgcm + Config.GridResolution / 2, YMitgcm + Config.GridResolution / 2
