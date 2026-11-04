"""Creation of the simulation folder: templates overlay, grid and bathymetry files."""
import os
import shutil
from pathlib import Path


# Folder holding the template folders that are overlaid to build a simulation folder
TEMPLATE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '00-template_mitgcm')


def remove_all_files_and_folders(FolderPath):
    """
    Empty a folder: delete all files and sub-folders inside it, but keep the folder itself.
    Input:
      FolderPath (str) - folder to empty
    Output:
      None
    """
    for ItemName in os.listdir(FolderPath):
        ItemPath = os.path.join(FolderPath, ItemName)
        if os.path.isdir(ItemPath):
            shutil.rmtree(ItemPath)
        else:
            os.remove(ItemPath)


def copy_template(TemplateFolder, OutputFolder):
    """
    Copy the content of a template folder into the output folder, overwriting files that already exist
    (so several templates can be overlaid in order).
    Inputs:
      TemplateFolder (str) - folder whose content is copied
      OutputFolder (str)   - destination folder (must exist)
    Output:
      None
    """
    for ItemName in os.listdir(TemplateFolder):
        SourcePath = os.path.join(TemplateFolder, ItemName)
        DestinationPath = os.path.join(OutputFolder, ItemName)
        if os.path.isdir(SourcePath):
            shutil.copytree(SourcePath, DestinationPath, dirs_exist_ok=True)
        else:
            shutil.copy2(SourcePath, DestinationPath)


def prepare_output_folder(Config):
    """
    Build an empty simulation folder from the templates: wipe the previous results of this simulation only
    (other simulations are kept), overlay the template folders listed in 'TemplateFolder' in order, and save
    the run settings in metadata_simulation.txt.
    Input:
      Config (ConfigObject) - run settings (SimulationName, TemplateFolder, Paths.PreprocessingOutputs)
    Output:
      OutputFolder (str) - path of the simulation folder, 2-preprocessing-outputs/<SimulationName>
    """
    OutputFolder = os.path.join(Config.Paths.PreprocessingOutputs, Config.SimulationName)

    # Remove the previous results of this simulation only
    if os.path.isdir(OutputFolder):
        remove_all_files_and_folders(OutputFolder)
    os.makedirs(OutputFolder, exist_ok=True)

    # Overlay the templates in order: later templates overwrite the files of earlier ones
    for TemplateName in Config.TemplateFolder:
        copy_template(os.path.join(TEMPLATE_ROOT, TemplateName), OutputFolder)

    Config.write_metadata_to_file(os.path.join(OutputFolder, 'metadata_simulation.txt'))
    return OutputFolder


def copy_grid_and_bathy(Config, OutputFolder):
    """
    Copy the grid files (.npy, .json, .csv) into <OutputFolder>/grid and the bathymetry into
    <OutputFolder>/binary_data/bathy.bin. Both are created beforehand with the grid_and_bathy/ notebooks.
    Inputs:
      Config (ConfigObject) - run settings (Paths.GridFolderPath, Paths.BathyPath)
      OutputFolder (str)    - simulation folder
    Output:
      None
    """
    # Grid files
    GridOutputFolder = os.path.join(OutputFolder, 'grid')
    os.makedirs(GridOutputFolder, exist_ok=True)
    for Extension in ['npy', 'json', 'csv']:
        for File in Path(Config.Paths.GridFolderPath).glob(f'*.{Extension}'):
            shutil.copy(File, GridOutputFolder)

    # Bathymetry (binary_data/ comes from the templates)
    shutil.copy(Config.Paths.BathyPath, os.path.join(OutputFolder, 'binary_data', 'bathy.bin'))
