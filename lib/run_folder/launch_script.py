"""Script that compiles and starts the simulation on the remote computer."""
import os

from lib.run_folder.templates import RESULTS_LINK
from lib.run_folder.watchdog import NORMAL_END_TEXT


def write_launch_script(OutputFolder, Config, NbCores, MitgcmResultsFolder, NbMakeJobs=4):
    """
    Write launch_simulation.sh at the root of the simulation folder. The data folder of the remote computer
    (Config.RemoteRoot, e.g. /storage/lake_zug_transport) mirrors the local data layout: the simulation folder is
    copied to <RemoteRoot>/2-preprocessing-outputs/<SimulationName>, and
    'bash <RemoteRoot>/2-preprocessing-outputs/<SimulationName>/launch_simulation.sh', run from any folder, compiles
    MITgcm, prepares the run folder and starts the simulation in the background with mpirun (results in
    <RemoteRoot>/3-MITgcm-outputs/<SimulationName>). Commands follow misc/tips/PenseBete_MITgcmAnne.txt and
    misc/tips/mitgcm_working_doc.pdf. Everything printed until MITgcm is started is also written to launch.log;
    if a step fails, the end of launch.log is emailed to NotifyEmail.
    Inputs:
      OutputFolder (str)        - simulation folder (contains code/, build/, run/, run_config/)
      Config (ConfigObject)     - run settings (RemoteRoot, MitgcmRootDir, BuildOptions, Watchdog.NotifyEmail,
                                  simulation and computer names)
      NbCores (int)             - number of MPI processes (Px * Py of SIZE.h)
      MitgcmResultsFolder (str) - absolute results folder on the remote computer
                                  (see get_mitgcm_results_folder)
      NbMakeJobs (int)          - number of parallel jobs for 'make'
    Output:
      (str) - path of the written script
    """
    Script = f'''#!/bin/bash
# Launch the MITgcm simulation '{Config.SimulationName}' on '{Config.ComputerName}'.
# Written by MAIN_preprocessing.ipynb. Remote layout (same as the local data folder):
#   {Config.RemoteRoot}/2-preprocessing-outputs/{Config.SimulationName}/   this folder, copied from the local computer
#   {Config.RemoteRoot}/3-MITgcm-outputs/{Config.SimulationName}/          MITgcm results (created by this script)
# Run from any folder:
#   bash {Config.RemoteRoot}/2-preprocessing-outputs/{Config.SimulationName}/launch_simulation.sh
# The MITgcm folder can be overridden: MITGCM_ROOTDIR=/path/to/MITgcm bash .../launch_simulation.sh
set -euo pipefail

# Folder of this script = simulation folder (works from any current directory)
SIM_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
export MITGCM_ROOTDIR="${{MITGCM_ROOTDIR:-{Config.MitgcmRootDir}}}"
BUILD_OPTIONS="$MITGCM_ROOTDIR/tools/build_options/{Config.BuildOptions}"

# Check the MITgcm installation before doing anything
[ -x "$MITGCM_ROOTDIR/tools/genmake2" ] || {{ echo "MITgcm not found in $MITGCM_ROOTDIR (set MITGCM_ROOTDIR)"; exit 1; }}
[ -f "$BUILD_OPTIONS" ] || {{ echo "Build options not found: $BUILD_OPTIONS"; exit 1; }}

# Check that the results folder can be created (before the compilation, which takes a few minutes)
RESULTS_DIR="{MitgcmResultsFolder}"
mkdir -p "$RESULTS_DIR" 2> /dev/null || {{ echo "Cannot create $RESULTS_DIR (no write access to {Config.RemoteRoot}?)"; exit 1; }}

# Copy of everything printed until MITgcm is started in launch.log (kept if the terminal is closed, downloaded
# with the results). The terminal's own outputs are saved in fd 3/4 to stop the copy before the progress bar
exec 3>&1 4>&2
exec > >(tee "$SIM_DIR/launch.log") 2>&1

# Email (subject $1, body $2) through the 'mail' command; only printed if no address or no 'mail' command
EMAIL="{Config.Watchdog['NotifyEmail']}"
send_mail() {{
  if [ -z "$EMAIL" ] || ! command -v mail > /dev/null; then
    echo "(no email sent: NotifyEmail empty in config.json or no 'mail' command on $(hostname))"
  elif printf '%s\\n' "$2" | mail -s "[MITgcm {Config.SimulationName}] $1" "$EMAIL"; then
    echo "Email '$1' handed to mail for $EMAIL"
  else
    echo "Email '$1' NOT sent: mail failed (exit $?)"
  fi
}}

# Any failing command from here on (set -e) stops the script: say where, and email the end of launch.log,
# since the watchdog (which sends the other emails) is not started yet
on_error() {{
  trap - ERR
  echo "=== FAILED at line $1 of launch_simulation.sh: see $SIM_DIR/launch.log ==="
  send_mail "FAILED during launch (line $1)" "$(tail -n 60 "$SIM_DIR/launch.log")"
  exit 1
}}
trap 'on_error $LINENO' ERR

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

# 3. Results folders, reached from run/ through the '{RESULTS_LINK}' symlink written in data.diagnostics and
# data.mnc (MITgcm truncates file names longer than 80 characters, so the absolute path is not used there)
mkdir -p "$RESULTS_DIR/outputs" "$RESULTS_DIR/to_delete"
ln -s "$RESULTS_DIR" {RESULTS_LINK}
echo "Results folder: $RESULTS_DIR (run/{RESULTS_LINK})"

# 4. Start the simulation on {NbCores} cores
# In the background and detached from the terminal (setsid: own session, nohup, disown), so the terminal can be
# closed and Ctrl+C on the progress bar does not reach MITgcm. The PID is saved for progress.sh
echo "=== Starting MITgcm (mpirun, {NbCores} cores) ==="
setsid nohup mpirun -np {NbCores} ./mitgcmuv > output_{Config.SimulationName}.out 2>&1 < /dev/null &
PID=$!
disown
echo "$PID" > mitgcm.pid

# 5. Watchdog (watchdog.sh): stops the run on NaN/unrealistic values, emails when it starts and when the run ends.
# Also detached from the terminal; its messages (and the result of each email) go to run/watchdog.log
setsid nohup bash ../watchdog.sh "$PID" > watchdog.log 2>&1 < /dev/null &
disown
if [ -z "$EMAIL" ]; then
  echo "Watchdog started, no email (NotifyEmail empty in config.json): see $SIM_DIR/run/watchdog.log"
elif ! command -v mail > /dev/null; then
  echo "Watchdog started, but no 'mail' command on $(hostname), so no email: see $SIM_DIR/run/watchdog.log"
else
  echo "Watchdog started: a 'started' email goes to $EMAIL now, another one when the run ends or is stopped."
  echo "  No 'started' email within a few minutes (spam folder too) = email does not work from $(hostname):"
  echo "  see $SIM_DIR/run/watchdog.log and test with: echo test | mail -s test $EMAIL"
fi

echo "MITgcm started (PID $PID). Useful commands:"
echo "  tail -f $SIM_DIR/run/STDOUT.0000    # follow the run (MITgcm log of the first core)"
echo "  grep '{NORMAL_END_TEXT}' $SIM_DIR/run/STDOUT.0000    # check that the run finished properly"
echo "  cat $SIM_DIR/run/output_{Config.SimulationName}.out $SIM_DIR/run/STDERR.0000    # errors (mpirun and MITgcm)"
echo "  ls $RESULTS_DIR/outputs    # results (3Dsnaps.*)"
echo "  ps aux | grep mpirun    # list the running simulations"
echo "  cat $SIM_DIR/run/watchdog.log    # watchdog messages"
echo "  bash $SIM_DIR/progress.sh    # progress bar (shown below)"
echo "  kill $PID    # stop this simulation (the watchdog then sends a FAILED email)"

# 6. Progress bar until the end of the run (Ctrl+C or closing the terminal only stops the display).
# MITgcm is started: no failure email from here on, and launch.log stops (the bar would fill it)
trap - ERR
exec 1>&3 2>&4 3>&- 4>&-
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
