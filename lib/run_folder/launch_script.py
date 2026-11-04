"""Script that compiles and starts the simulation on the remote computer."""
import os


def write_launch_script(OutputFolder, Config, NbCores, MitgcmResultsFolder, NbMakeJobs=4):
    """
    Write launch_simulation.sh at the root of the simulation folder. kball_laken mirrors the local data layout:
    the simulation folder is copied to <remote root>/2-preprocessing-outputs/, and from <remote root>
    'bash 2-preprocessing-outputs/<SimulationName>/launch_simulation.sh' compiles MITgcm, prepares the run folder
    and starts the simulation in the background with mpirun (results in <remote root>/3-MITgcm-outputs/). Commands follow misc/tips/PenseBete_MITgcmAnne.txt and
    misc/tips/mitgcm_working_doc.pdf.
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

# 1a. Clean build folder (files of a previous, possibly failed, compilation would be reused by make)
cd "$SIM_DIR/build"
find . -mindepth 1 ! -name READ_ME.md -delete

# 1b. MPI header folder (mpif.h): the build options only pass it to the compiler through MPI_INC_DIR.
# Taken from the MPI compiler wrapper (OpenMPI: --showme:incdirs, MPICH: -show), else searched in /usr and /opt
if [ -z "${{MPI_INC_DIR:-}}" ]; then
  for Dir in $(mpif77 --showme:incdirs 2>/dev/null) $(mpif77 -show 2>/dev/null | tr ' ' '\\n' | sed -n 's/^-I//p'); do
    if [ -f "$Dir/mpif.h" ]; then MPI_INC_DIR="$Dir"; break; fi
  done
fi
if [ -z "${{MPI_INC_DIR:-}}" ]; then
  MPI_INC_DIR="$(dirname "$(find /usr /opt -name mpif.h -print -quit 2>/dev/null)")"
fi
[ -f "$MPI_INC_DIR/mpif.h" ] || {{ echo "mpif.h not found: set MPI_INC_DIR=/path/to/mpi/include"; exit 1; }}
export MPI_INC_DIR
echo "MPI headers: $MPI_INC_DIR"

# 1c. Build options: copy of the MITgcm file, adapted to recent compilers (the MITgcm folder is not modified)
#   - gcc >= 14 rejects old C code (e.g. sprintf without stdio.h in setdir.c): turn these errors back into warnings
#   - gfortran >= 10 rejects MPI calls with different argument types: -fallow-argument-mismatch
OPTFILE="$SIM_DIR/build/{Config.BuildOptions}_compat"
cp "$BUILD_OPTIONS" "$OPTFILE"
cat >> "$OPTFILE" << 'EOF'

# Added by launch_simulation.sh: compatibility of old MITgcm checkpoints with recent compilers
CFLAGS="$CFLAGS -Wno-error=implicit-function-declaration -Wno-error=implicit-int -Wno-error=incompatible-pointer-types -Wno-error=int-conversion"
EOF
GFORTRAN_MAJOR="$(mpif77 -dumpversion | cut -d. -f1)"
if [ "$GFORTRAN_MAJOR" -ge 10 ]; then
  echo 'FFLAGS="$FFLAGS -fallow-argument-mismatch"; F90FLAGS="$F90FLAGS -fallow-argument-mismatch"' >> "$OPTFILE"
fi
echo "Build options: $OPTFILE (gfortran $GFORTRAN_MAJOR)"

# 1d. Makefile, dependencies and compilation
"$MITGCM_ROOTDIR/tools/genmake2" -mods ../code -mpi -enable=mnc -of "$OPTFILE"
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
# In the background and detached from the terminal (setsid: own session, nohup, disown), so the terminal can be
# closed and Ctrl+C on the progress bar does not reach MITgcm. The PID is saved for progress.sh
echo "=== Starting MITgcm (mpirun, {NbCores} cores) ==="
setsid nohup mpirun -np {NbCores} ./mitgcmuv > output_{Config.SimulationName}.out 2>&1 < /dev/null &
PID=$!
disown
echo "$PID" > mitgcm.pid

# 5. Watchdog (watchdog.sh): stops the run on NaN/unrealistic values and sends an email when the run ends.
# Also detached from the terminal; its messages go to run/watchdog.log
setsid nohup bash ../watchdog.sh "$PID" > watchdog.log 2>&1 < /dev/null &
disown
EMAIL="{Config.Watchdog['NotifyEmail']}"
if [ -z "$EMAIL" ]; then
  echo "Watchdog started, no email (NotifyEmail empty in config.json): see $SIM_DIR/run/watchdog.log"
elif ! command -v mail > /dev/null; then
  echo "Watchdog started, but no 'mail' command on this computer: see $SIM_DIR/run/watchdog.log"
else
  echo "Watchdog started: email to $EMAIL when the run ends or is stopped"
fi

echo "MITgcm started (PID $PID). Useful commands:"
echo "  tail -f $SIM_DIR/run/STDOUT.0000    # follow the run (MITgcm log of the first core)"
echo "  grep 'NORMAL END' $SIM_DIR/run/STDOUT.0000    # check that the run finished properly"
echo "  cat $SIM_DIR/run/output_{Config.SimulationName}.out $SIM_DIR/run/STDERR.0000    # errors (mpirun and MITgcm)"
echo "  ls $RESULTS_DIR/outputs    # results (3Dsnaps.*)"
echo "  ps aux | grep mpirun    # list the running simulations"
echo "  cat $SIM_DIR/run/watchdog.log    # watchdog messages"
echo "  bash $SIM_DIR/progress.sh    # progress bar (shown below)"
echo "  kill $PID    # stop this simulation (the watchdog then sends a FAILED email)"

# 6. Progress bar until the end of the run (Ctrl+C or closing the terminal only stops the display)
echo
echo "=== Progress (Ctrl+C stops the display, not the simulation) ==="
bash "$SIM_DIR/progress.sh"
'''
    # Unix line endings (the script runs on Linux even if written on Windows), and executable
    ScriptPath = os.path.join(OutputFolder, 'launch_simulation.sh')
    with open(ScriptPath, 'w', newline='\n') as File:
        File.write(Script)
    os.chmod(ScriptPath, 0o755)

    return ScriptPath
