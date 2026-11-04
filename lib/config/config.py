import json
import os
import re


def resolve_path(RawPath, DataRoot):
    """
    Convert a path from config.json into a usable absolute path.
    Inputs:
      RawPath (str)  - path from config.json: relative to DataRoot, or absolute (e.g. 'C:/Users/...')
      DataRoot (str) - root folder holding all data files (already resolved), or None
    Output:
      (str) - absolute path. A Windows drive path ('C:/...') becomes '/c/...' when not running on Windows,
              otherwise it would be read as a relative folder named 'C:'.
    """
    RawPath = RawPath.replace('\\', '/')
    # Map Windows drive letters to their mount point on POSIX shells (e.g. Git Bash, WSL-like mounts)
    if os.name != 'nt' and re.match(r'^[A-Za-z]:/', RawPath):
        RawPath = f'/{RawPath[0].lower()}{RawPath[2:]}'
    # Relative paths are relative to the data root
    if DataRoot is not None and not os.path.isabs(RawPath):
        RawPath = os.path.join(DataRoot, RawPath)
    return os.path.normpath(RawPath)


class Paths:
    """
    All file and folder paths used by the preprocessing (attributes in PascalCase, all absolute paths).
    Inputs:
      LakeName (str)           - name of the lake (key in config.json)
      LakeConfig (dict)        - config.json['GridConfig'][LakeName]
      GridConfig (dict)        - config.json['GridConfig'][LakeName][GridConfigName]
      WeatherModelConfig (dict) - config.json['WeatherModelConfig'][WeatherModel]
      DataRoot (str)           - resolved root folder of the data files (inputs and outputs)
    """
    def __init__(self, LakeName, LakeConfig, GridConfig, WeatherModelConfig, DataRoot):
        # Data folders (see LZT_datafiles)
        self.DataRoot = DataRoot
        self.PreprocessingInputs = os.path.join(DataRoot, '1-preprocessing-inputs')
        self.PreprocessingOutputs = os.path.join(DataRoot, '2-preprocessing-outputs')
        self.MitgcmOutputs = os.path.join(DataRoot, '3-MITgcm-outputs')
        self.PostprocessingOutputs = os.path.join(DataRoot, '4-postprocessing-outputs')

        # Lake and grid input files
        self.GridFolderPath = resolve_path(GridConfig['GridFolderPath'], DataRoot)
        self.BathyPath = resolve_path(GridConfig['BathyPath'], DataRoot)
        self.RawBathyPath = resolve_path(LakeConfig['RawBathyPath'], DataRoot)
        self.ShorelinePath = resolve_path(LakeConfig['ShorelinePath'], DataRoot)

        # Downloaded inputs (weather from the Alplakes API, Simstrat profiles for the initial conditions)
        RawWeatherRoot = resolve_path(WeatherModelConfig['RawResultsFromApiFolder'], DataRoot)
        self.RawWeatherFolder = os.path.join(RawWeatherRoot, LakeName)
        self.SimstratFolder = os.path.join(self.PreprocessingInputs, 'simstrat_data', LakeName)


class River:
    """
    One river (inflow or outflow) of the lake, as defined in config.json['RiverConfig'].
    Inputs:
      Name (str)           - river name (key in the river config)
      RiverConfig (dict)   - config.json['RiverConfig'][LakeName][Name]
      GridConfigName (str) - name of the grid, selects the river mouth coordinates for this grid
    """
    def __init__(self, Name, RiverConfig, GridConfigName):
        self.Name = Name
        self.BafuId = RiverConfig['BafuId']
        self.DischargeVariableName = RiverConfig['DischargeVariableName']
        self.TemperatureVariableName = RiverConfig['TemperatureVariableName']
        self.CoordinatesLakePoint = RiverConfig['CoordinatesLakePoint'][GridConfigName]
        self.Direction = RiverConfig['Direction']
        self.InOrOut = RiverConfig['InOrOut']
        self.RiverDepth = RiverConfig['RiverDepth']


# Calibration parameters: taken from config.json['Calibration'][lake], else from the 'Default' block
CALIBRATION_KEYS = ['Secchi', 'ALw', 'exf_albedo', 'viscC2smag', 'viscAhGrid', 'diffKhT', 'viscAz', 'diffKzT',
                    'cdrag_1', 'cdrag_2', 'cdrag_3', 'bottomDragQuadratic']


class ConfigObject:
    """
    Settings of the current run, read from the 'current_project' block of config.json and resolved against the
    lake, grid, calibration, computer and weather model blocks. All attributes are in PascalCase.
    Input:
      ConfigFilePath (str) - path to config.json
    """
    def __init__(self, ConfigFilePath):
        with open(ConfigFilePath, 'r') as File:
            Config = json.load(File)

        # Root folder of all data files (inputs and outputs)
        DataRoot = resolve_path(Config['DataRoot'], None)

        # Run definition
        CurrentProject = Config['CurrentProject']
        self.SimulationName = CurrentProject['SimulationName']
        self.LakeName = CurrentProject['LakeName']
        self.GridConfigName = CurrentProject['GridConfigName']
        self.StartDate = CurrentProject['StartDate']
        self.EndDate = CurrentProject['EndDate']
        self.ReferenceDate = CurrentProject['ReferenceDate']
        self.WeatherModel = CurrentProject['WeatherModel']
        self.TemplateFolder = CurrentProject['TemplateFolder']
        self.InitializationType = CurrentProject['InitializationType']
        self.WithRivers = CurrentProject['WithRivers']

        # Lake characteristics
        LakeConfig = Config['GridConfig'][self.LakeName]
        self.EpsgProjection = LakeConfig.get('EpsgProjection', '2056')
        self.NoDataRawBathy = LakeConfig['NoDataRawBathy']
        self.LakeAltitude = LakeConfig['LakeAltitude']

        # Lake calibration: lake-specific value if given, otherwise the default one
        CalibrationConfig = Config['Calibration'][self.LakeName]
        DefaultParameters = Config['Calibration']['Default']
        for Key in CALIBRATION_KEYS:
            setattr(self, Key, CalibrationConfig.get(Key, DefaultParameters[Key]))

        # Grid parameters
        GridConfig = LakeConfig[self.GridConfigName]
        self.GridResolution = GridConfig['GridResolution']
        self.TimeStep = GridConfig['TimeStep']
        self.X0 = GridConfig['X0']
        self.Y0 = GridConfig['Y0']
        self.Rotation = GridConfig['Rotation']
        self.Nx = GridConfig['Nx']
        self.Ny = GridConfig['Ny']

        # Rivers (only if requested)
        if self.WithRivers:
            RiverConfig = Config['RiverConfig'].get(self.LakeName, {})
            self.Rivers = [River(Name, Value, self.GridConfigName) for Name, Value in RiverConfig.items()]

        # Remote computer running MITgcm (kball_laken)
        ComputerConfig = Config['ComputerConfig']
        self.ComputerName = ComputerConfig['Name']
        self.ResultsFolder = ComputerConfig['ResultsFolder']  # results folder on the remote computer
        self.MitgcmRootDir = ComputerConfig['MitgcmRootDir']  # MITgcm source folder on the remote computer
        self.BuildOptions = ComputerConfig['BuildOptions']    # file of MITgcm tools/build_options for genmake2
        self.Px = ComputerConfig[self.LakeName][self.GridConfigName]['Px']
        self.Py = ComputerConfig[self.LakeName][self.GridConfigName]['Py']

        # Weather model
        WeatherModelConfig = Config['WeatherModelConfig'][self.WeatherModel]
        self.WeatherApiBaseUrl = WeatherModelConfig['BaseUrl']
        self.WeatherDownloadBuffer = WeatherModelConfig['Buffer']
        self.WeatherModelType = WeatherModelConfig['Type']

        # Paths
        self.Paths = Paths(self.LakeName, LakeConfig, GridConfig, WeatherModelConfig, DataRoot)

    def write_metadata_to_file(self, OutputFilePath):
        """
        Write all settings of the run to a text file, for traceability of the generated simulation folder.
        Input:
          OutputFilePath (str) - path of the text file to write
        Output:
          None - the file is written
        """
        with open(OutputFilePath, 'w') as File:
            File.write('ConfigObject Metadata\n')
            File.write('=====================\n\n')

            for Name, Value in vars(self).items():
                # The Paths object is written as an indented sub-list
                if isinstance(Value, Paths):
                    File.write(f'{Name}:\n')
                    for PathName, PathValue in vars(Value).items():
                        File.write(f'  {PathName}: {PathValue}\n')
                else:
                    File.write(f'{Name}: {Value}\n')
