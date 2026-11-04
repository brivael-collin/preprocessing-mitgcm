# preprocessing-mitgcm

Builds a ready-to-compile MITgcm run folder for Lake Zug (or the synthetic `dummy_rectangle` test basin).
The whole run is defined in `config.json`. `MAIN_preprocessing.ipynb` turns it into
`LZT_datafiles/2-preprocessing-outputs/<SimulationName>/`, a folder you copy to kball_laken and start with one command.

- [Quick start](#quick-start)
- [Data folders](#data-folders)
- [Configuration](#configuration-configjson)
- [Pipeline step by step](#pipeline-step-by-step-main_preprocessingipynb)
- [Code structure](#code-structure)
- [Standalone notebooks](#standalone-notebooks-notebooks)
- [Template folders](#template-folders-00-template_mitgcm)
- [Output folder](#output-folder)
- [Conventions and how to extend](#conventions-and-how-to-extend)

---

## Quick start
1. **Python environment** (once). Create it outside the repo, because the repo folder does not allow the symlinks a venv needs:
   ```bash
   uv venv ~/.venvs/lzt && uv pip install --python ~/.venvs/lzt/bin/python -r ../misc/requirements.txt
   ```
   Use the Jupyter kernel "Python (LakeZug)".
2. **Inputs** (once per lake and grid). The grid, bathymetry and land-tile files must exist in `1-preprocessing-inputs`. Create them with the notebooks in `notebooks/grid_and_bathy/` (see [Standalone notebooks](#standalone-notebooks-notebooks)).
3. **Choose the run** in the `CurrentProject` block of `config.json`.
4. **Run** `MAIN_preprocessing.ipynb` from top to bottom. The kernel's working directory must be `preprocessing-mitgcm/`.
5. **Launch on kball_laken**: copy the output folder there (`scp -r` or WinSCP), then run:
   ```bash
   bash <simulation folder>/launch_simulation.sh
   ```

---

## Data folders
No data lives in the repo. All data is under `DataRoot` (set in `config.json`), `C:\Users\collinbr\Desktop\LZT_datafiles`:

| Folder | Content | Access |
|---|---|---|
| `1-preprocessing-inputs/` | grid files (`x.npy`, `y.npy`, `lat_grid.npy`, `lon_grid.npy`, `dz.csv`, `parameters.json`), `bathy.bin`, `land_cores_Px*_Py*.txt`, raw bathymetry, shoreline, `raw_from_alplakes_api/<lake>/` (weather), `simstrat_data/<lake>/` | writable: missing weather and Simstrat files are downloaded here automatically |
| `2-preprocessing-outputs/` | one folder per simulation, written by this pipeline | rebuilt by MAIN |
| `3-MITgcm-outputs/` | MITgcm results | **read-only** |
| `4-postprocessing-outputs/` | results of `postprocessing-mitgcm/` | |

Paths in `config.json` are relative to `DataRoot`. The code accesses them only through `Config.Paths.*` (`lzt_config.resolve_path` also maps `C:/...` to `/c/...` on Linux). Never hard-code a data path in a notebook.

---

## Configuration (`config.json`)
`ConfigObject` (`lzt_config/config.py`) reads the `CurrentProject` block. It then looks up everything else by lake, grid and weather-model name, and exposes all of it as attributes (`Config.TimeStep`, `Config.Px`, `Config.Paths.GridFolderPath`, ...).

**`CurrentProject`**: what to run. The simulation name (name of the output folders) is built automatically from it:
`<LakeName>_<GridConfigName>_<StartDate>-<EndDate>[_ref<ReferenceDate>]_<WeatherModel>[_<SimulationLabel>]`, e.g. `zug_100m_20250101-20250301_icon`. The reference date appears only when it differs from the start date.

| Key | Example | Meaning |
|---|---|---|
| `SimulationLabel` | `""` or `lowdrag` | optional free label appended to the simulation name |
| `LakeName` | `zug` | key used in all the lookup blocks below |
| `GridConfigName` | `100m` | grid inside `GridConfig[lake]` |
| `StartDate`, `EndDate` | `20250101`, `20250301` | simulated period (`YYYYMMDD`) |
| `ReferenceDate` | `20250101` | time origin of MITgcm (t = 0 s) |
| `WeatherModel` | `icon` | key in `WeatherModelConfig` |
| `TemplateFolder` | `["default", "exch2", "obcs", "crop_results"]` | template folders overlaid in this order |
| `InitializationType` | `simstrat` or `pickup` | how the initial state is built |
| `WithRivers` | `false` | add rivers as open boundaries |

**Lookup blocks**

| Block | Content |
|---|---|
| `GridConfig[lake][grid]` | resolution, time step, origin, rotation, `Nx`, `Ny`, grid folder and bathy paths |
| `Calibration[lake]` (falls back to `Calibration.Default`) | Secchi depths, `ALw`, `exf_albedo`, `cdrag_1..3`, viscosities and diffusivities (`viscAz`, `diffKzT`, `viscC2smag`, `viscAhGrid`, `diffKhT`, `bottomDragQuadratic`) |
| `WeatherModelConfig[model]` | Alplakes API url, download buffer around the grid, `reanalysis` or `forecast` |
| `ComputerConfig` | kball_laken: results folder, MITgcm source folder, build options, `Px` / `Py` per lake and grid |
| `RiverConfig[lake]` | per river: BAFU id, variable names, mouth position on each grid, boundary direction, depth (only if `WithRivers`) |

---

## Pipeline step by step (`MAIN_preprocessing.ipynb`)
The notebook has 9 numbered sections. Each one is one or two library calls followed by a printed check.

### 1. Setup
Imports the libraries, loads `config.json` and computes the start and end of the run in seconds from the reference date (`get_run_times`). Prints a summary of the run.

### 2. Prepare the output folder (`run_folder.prepare_output_folder`)
- Empties `2-preprocessing-outputs/<SimulationName>/`. Other simulations are not touched.
- Copies each folder of `TemplateFolder` from `00-template_mitgcm/`, in order. A later template overwrites the files of an earlier one.
- Writes `metadata_simulation.txt`, a copy of the settings used.

### 3. Grid and bathymetry (`run_folder.copy_grid_and_bathy`, `grid_and_bathy.get_grid`)
Copies the grid files (`.npy`, `.json`, `.csv`) to `grid/` and the bathymetry to `binary_data/bathy.bin`. Then it loads the horizontal grid (`MitgcmGrid`) and the layer thicknesses (`dz.csv`).

### 4. Surface forcings (`surface_forcings`)
- `download_weather`: downloads the missing days from the Alplakes API into `1-preprocessing-inputs/raw_from_alplakes_api/<lake>/`. It covers the grid's bounding box plus a buffer. Days already present are skipped.
- `extract_and_save_surface_forcings`: interpolates each weather variable to the grid and writes one big-endian `>f8` binary per variable to `binary_data/`:
  - `u10`, `v10`: wind
  - `swdown`: shortwave
  - `atemp`: air temperature
  - `apressure`: pressure
  - `relhum`: relative humidity
  - `clct`: cloud cover
  - `aqh`: specific humidity, computed from the others
  - `lwdown`: longwave radiation, computed with the calibration factor `ALw`

### 5. Initial conditions (`initial_conditions.build_initial_conditions`)
- `simstrat`: takes the Alplakes Simstrat temperature profile closest to the start date and interpolates it to the model layers. The profile is downloaded into `1-preprocessing-inputs/simstrat_data/<lake>/` if missing.
- `pickup`: restarts from a MITgcm pickup file. The pickup number is the number of time steps since the reference date, and the temperature passed to MITgcm is only a placeholder.
- In both cases, salinity is a constant default (0.03).

### 6. Fill the template files (`run_folder`)
The copied template files contain `!placeholder!` tokens. Only the copies in the output folder are filled, never the files in `00-template_mitgcm/`.
- `fill_run_config_templates`:
  - `data.cal`: reference date
  - `data.exf`: start date, albedo, wind drag coefficients
  - `data.diagnostics`, `data.mnc`: results folders on kball_laken
  - `postprocessing/*.py`: reference date, time step, results folder
- `write_secchi`: Secchi depths in `code/swfrac.F` (light penetration)
- `write_data_config_files`: `run_config/data` (time step, start and end, pickup, initial T/S, vertical grid, viscosities and diffusivities)

### 7. Domain decomposition (`run_folder.write_exch2_config`, `write_size_config_files`)
Fills `code/SIZE.h` (`Nx`, `Ny`, `Nr`, `Px`, `Py`, `sNx`, `sNy`). With the `exch2` template, tiles made only of land are dropped. The land tiles are read from `land_cores_Px{Px}_Py{Py}.txt` (written by `notebooks/grid_and_bathy/check_core_allocation.ipynb`). The remaining `Px*Py - n_land` tiles are laid out in a single row (`Py = 1`), which reduces the number of cores needed.

### 8. Rivers (optional, `rivers`)
Only runs if `WithRivers` is true. It finds each river mouth on the grid and fills `data.obcs` with the open-boundary settings (`build_river_config`). It also writes the boundary velocity and temperature binaries from the BAFU discharge and temperature data (`build_river_binaries`).

### 9. Launch script (`run_folder.write_launch_script`)
Writes `launch_simulation.sh`. On kball_laken, this script:
1. compiles MITgcm with the simulation's `code/` (`genmake2`, `make`)
2. builds a clean `run/` folder
3. creates the results folders
4. starts `mpirun` in the background

The MITgcm folder can be overridden with `MITGCM_ROOTDIR=/path/to/MITgcm bash launch_simulation.sh`.

---

## Code structure
```
preprocessing-mitgcm/
├── MAIN_preprocessing.ipynb    main pipeline (sections 1-9 above)
├── config.json                 run settings
├── 00-template_mitgcm/         MITgcm template folders (see below)
├── lzt_config/
│   └── config.py               ConfigObject, Paths, River, resolve_path
├── lzt_utils/
│   ├── io.py                   modify_arguments (fills !placeholder!), write_binary, load_json, convert_binary_files
│   └── http.py                 try_download, fetch_and_save
├── grid_and_bathy/
│   └── grid.py                 MitgcmGrid, grid building and rotation, get_grid, get_dz_grid, coordinate conversion
├── run_folder/
│   ├── output_folder.py        prepare_output_folder, copy_template, copy_grid_and_bathy
│   ├── templates.py            get_run_times, fill_run_config_templates, write_data_config_files,
│   │                           write_size_config_files, write_secchi, write_exch2_config
│   └── launch_script.py        write_launch_script
├── surface_forcings/
│   ├── download.py             download_weather (Alplakes reanalysis / forecast)
│   ├── interpolation.py        json -> grid interpolation, extract_and_save_surface_forcings
│   └── physics.py              specific humidity, vapour pressure, longwave radiation
├── initial_conditions/
│   ├── profiles.py             build_initial_conditions, profile -> model layers
│   ├── simstrat.py             download and read Alplakes Simstrat profiles
│   └── datalakes.py            Datalakes (Eawag) measured profiles, not used by MAIN
├── rivers/
│   └── rivers.py               river open boundaries: obcs config and binaries
└── notebooks/                  standalone one-off notebooks (see below)
```

- **Libraries hold `.py` files only.** Notebooks live in `notebooks/`.
- **Import from the package, not the module.** Each package's `__init__.py` re-exports its public functions, e.g. `from run_folder import write_launch_script`.
- **Dependencies between packages:** `lzt_config` and `lzt_utils` are the base. `grid_and_bathy` is used by `rivers`. The other packages only use `lzt_utils` and the `Config` object passed in.

---

## Standalone notebooks (`notebooks/`)
These are one-off steps that produce the inputs MAIN reads, plus some checks. Each one starts with `sys.path.append('../..')` and loads `ConfigObject('../../config.json')`, so it runs from its own folder.

| Notebook | Purpose |
|---|---|
| `grid_and_bathy/merge_swissbathy_tiles` | merge swissBATHY3D `.asc` tiles into one `.tif` |
| `grid_and_bathy/create_grid` | build the rotated MITgcm grid and save `x/y/lat/lon` `.npy` + `parameters.json` |
| `grid_and_bathy/create_bathy` | average the measured bathymetry per grid cell (or reload a gpkg edited in QGIS) and write `bathy.bin` |
| `grid_and_bathy/check_core_allocation` | find the tiles that contain only land for a given `Px x Py` and write `land_cores_Px*_Py*.txt` (needed with `exch2`) |
| `surface_forcings/create_surf_force` | step-by-step, exploratory version of the surface forcing interpolation |
| `surface_forcings/create_dummy_surface_forcing` | synthetic forcings (wind event, constant fluxes) for test basins |
| `initial_conditions/create_initial_TS` | initial T/S from CTD profiles (legacy, hard-coded paths of the original author) |
| `rivers/download_bafu_data` | download hourly BAFU discharge for each river |
| `rivers/build_river_config`, `rivers/build_river_binaries` | run the river steps of MAIN on their own |
| `rivers/display_binary_files` | plot the river boundary binaries |
| `tools/check_output` | plot the binaries of a generated simulation (bathymetry, boundary conditions) |
| `tools/convert_endian_binary_files` | convert binaries between big- and little-endian |
| `tools/convert_grid_coordinates` | convert points between projected and MITgcm grid coordinates |

---

## Template folders (`00-template_mitgcm/`)
Each folder holds the MITgcm files of one feature. `TemplateFolder` lists the folders to combine.

| Folder | Content |
|---|---|
| `default` | base setup: `code/` (`SIZE.h`, `CPP_OPTIONS.h`, `packages.conf`, `swfrac.F`, ...), `run_config/` (`data`, `data.cal`, `data.exf`, `data.diagnostics`, `data.mnc`, ...), `binary_data/` |
| `exch2` | `W2_EXCH2_SIZE.h`, `data.exch2`, packages to drop land tiles |
| `obcs` | open boundaries (`data.obcs`, `data.pkg`, `data.exf`), needed for rivers |
| `crop_results` | postprocessing scripts that extract surface and station results |
| `crop_results_advanced` | extra postprocessing (heat fluxes, KPP, statistics) |
| `zug` | Zug-specific `data` and `data.kpp` |
| `heat_fluxes_analysis`, `swirl`, `postprocessing`, `EOF_synthetic`, `bk_config` | specific analyses and older setups |

---

## Output folder
`2-preprocessing-outputs/<SimulationName>/` contains:
```
code/                    MITgcm compile-time files (SIZE.h, packages.conf, swfrac.F, ...)
run_config/              MITgcm namelists (data, data.cal, data.exf, data.diagnostics, data.mnc, data.exch2, data.obcs, ...)
binary_data/             bathy.bin and the forcing binaries (big-endian >f8)
grid/                    copy of the grid files
postprocessing/          scripts run next to MITgcm
build/, run/             empty, filled on kball_laken by launch_simulation.sh
launch_simulation.sh     compile + run script
metadata_simulation.txt  settings used for this run
```