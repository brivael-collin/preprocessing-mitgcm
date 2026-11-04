"""Script that compiles and starts the simulation on the remote computer."""
import os


def write_launch_script(OutputFolder, Config, NbCores, MitgcmResultsFolder, NbMakeJobs=4):
    """
    Write launch_simulation.sh at the root of the simulation folder. kball_laken mirrors the local data layout:
    the simulation folder is copied to <remote root>/2-preprocessing-outputs/, and from <remote root>
    'bash 2-preprocessing-outputs/<SimulationName>/launch_simulation.sh' compiles MITgcm, prepares the run folder
    and starts the simulation in the background with mpirun (results in <remote root>/3-MITgcm-outputs/). Commands follow tips/PenseBete_MITgcmAnne.txt and
    tips/mitgcm_working_doc.pdf.
    Inputs:
      OutputFolder (str)        - simulation folder (contains code/, build/, run/, run_config/)
      Config (ConfigObject)     - run settings (MitgcmRootDir, BuildOptions, simulation and computer names)
      NbCores (int)             - number of MPI processes (Px * Py of SIZE.h)
      MitgcmResultsFolder (str) - results folder on the remote computer, absolute or relative to run/
                                  (see get_mitgcm_results_folder)
      NbMakeJobs (int)          - number of parallel jobs for 'make'
    Output:
      (str) - path of the written script
    """
    Script = f'''#!/bin/bash
# Launch the MITgcm simulation '{Config.SimulationName}' on '{Config.ComputerName}'.
# Written by MAIN_preprocessing.ipynb. Remote layout (same as the local data folder):
#   <root>/2-preprocessing-outputs/{Config.SimulationName}/   this folder, copied from the local computer
#   <root>/3-MITgcm-outputs/{Config.SimulationName}/          MITgcm results (created by this script)
# Run from <root>:
#   bash 2-preprocessing-outputs/{Config.SimulationName}/launch_simulation.sh
# The MITgcm folder can be overridden: MITGCM_ROOTDIR=/path/to/MITgcm bash 2-preprocessing-outputs/...
set -euo pipefail

# Check that the terminal is in <root> (the folder containing 2-preprocessing-outputs/)
[ -d 2-preprocessing-outputs ] || {{ echo "Run this script from the folder containing 2-preprocessing-outputs/ and 3-MITgcm-outputs/"; exit 1; }}

# Folder of this script = simulation folder (works from any current directory)
SIM_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
export MITGCM_ROOTDIR="${{MITGCM_ROOTDIR:-{Config.MitgcmRootDir}}}"
BUILD_OPTIONS="$MITGCM_ROOTDIR/tools/build_options/{Config.BuildOptions}"

# Check the MITgcm installation before doing anything
[ -x "$MITGCM_ROOTDIR/tools/genmake2" ] || {{ echo "MITgcm not found in $MITGCM_ROOTDIR (set MITGCM_ROOTDIR)"; exit 1; }}
[ -f "$BUILD_OPTIONS" ] || {{ echo "Build options not found: $BUILD_OPTIONS"; exit 1; }}

# 1. Compile MITgcm with the code of this simulation
echo "=== Compiling MITgcm ($(date '+%Y-%m-%d %H:%M:%S')) ==="
cd "$SIM_DIR/build"
"$MITGCM_ROOTDIR/tools/genmake2" -mods ../code -mpi -enable=mnc -of "$BUILD_OPTIONS"
make depend
make -j {NbMakeJobs}

# 2. Prepare a clean run folder: executable, run parameters, pickup files and postprocessing scripts
echo "=== Preparing the run folder ==="
cd "$SIM_DIR"
rm -rf run
mkdir run
cd run
cp ../build/mitgcmuv .
ln -s ../run_config/* .
if [ -d ../pickup ]; then ln -s ../pickup/* .; fi
if [ -d ../postprocessing ]; then ln -s ../postprocessing/* .; fi

# 3. Results folders (paths written in data.diagnostics and data.mnc; relative paths start from run/)
mkdir -p "{MitgcmResultsFolder}/outputs" "{MitgcmResultsFolder}/to_delete"
RESULTS_DIR="$(cd "{MitgcmResultsFolder}" && pwd)"
echo "Results folder: $RESULTS_DIR"

# 4. Start the simulation on {NbCores} cores
# In the background and detached from the terminal (nohup, disown), so the terminal can be closed
echo "=== Starting MITgcm (mpirun, {NbCores} cores) ==="
nohup mpirun -np {NbCores} ./mitgcmuv > output_{Config.SimulationName}.out 2>&1 < /dev/null &
PID=$!
disown
echo "MITgcm started (PID $PID). Useful commands:"
echo "  tail -f $SIM_DIR/run/output_{Config.SimulationName}.out    # follow the run"
echo "  grep 'NORMAL END' $SIM_DIR/run/STDOUT.0000    # check that the run finished properly"
echo "  ls $RESULTS_DIR/outputs    # results (3Dsnaps.*)"
echo "  ps aux | grep mpirun    # list the running simulations"
echo "  kill $PID    # stop this simulation"
'''
    # Unix line endings (the script runs on Linux even if written on Windows), and executable
    ScriptPath = os.path.join(OutputFolder, 'launch_simulation.sh')
    with open(ScriptPath, 'w', newline='\n') as File:
        File.write(Script)
    os.chmod(ScriptPath, 0o755)

    return ScriptPath
