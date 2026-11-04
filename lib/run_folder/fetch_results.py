"""Script run on the remote computer that sends the results of a finished simulation to the local computer."""
import os


def write_fetch_results_script(OutputFolder, Config, MitgcmResultsFolder):
    """
    Write fetch_results.sh at the root of the simulation folder. 'Fetch results from kball_laken.bat' (local Windows
    computer) runs it through ssh: 'ssh <host> "bash 2-preprocessing-outputs/<sim>/fetch_results.sh" | tar -xf -'.
    The script checks that the run finished without errors (MITgcm not running anymore, 'NORMAL END' in STDOUT.0000)
    and, only then, writes the results folder as a tar archive to stdout. Messages and the per-file progress go to
    stderr, so they are shown in the local terminal without mixing with the archive. Check and download use the same
    ssh connection (one password).
    Inputs:
      OutputFolder (str)        - simulation folder
      Config (ConfigObject)     - run settings (SimulationName)
      MitgcmResultsFolder (str) - results folder on the remote computer, absolute or relative to run/
    Output:
      (str) - path of the written script
    """
    Script = f'''#!/bin/bash
# Sends the results of the MITgcm simulation '{Config.SimulationName}' as a tar archive on stdout, only if the run
# finished without errors. Written by MAIN_preprocessing.ipynb; run by 'Fetch results from kball_laken.bat':
#   ssh <host> "bash 2-preprocessing-outputs/{Config.SimulationName}/fetch_results.sh" | tar -xf - -C <local folder>
# All messages go to stderr (stdout carries the archive only).
set -o pipefail
SIM_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
refuse() {{ echo "kball: download refused: $1" >&2; exit 1; }}

# 1. Checks: launched, not running anymore, finished properly
cd "$SIM_DIR/run" 2> /dev/null || refuse "the simulation was not launched (no run folder)"
if [ -f mitgcm.pid ] && kill -0 "$(cat mitgcm.pid)" 2> /dev/null; then
  refuse "the simulation is still running (bash $SIM_DIR/progress.sh on kball to follow it)"
fi
grep -q "NORMAL END" STDOUT.0000 2> /dev/null || \\
  refuse "the simulation did not finish properly (see $SIM_DIR/run/watchdog.log and STDERR.0000 on kball)"
RESULTS="$(cd "{MitgcmResultsFolder}" 2> /dev/null && pwd)" || refuse "no results folder {MitgcmResultsFolder}"

# 2. Marker included in the archive: the .bat deletes its local copy before downloading and checks it is back,
# so an old local copy is never taken for a successful download
date '+%Y-%m-%d %H:%M:%S' > "$RESULTS/download_check.txt"

# 3. Size of the download
NbFiles=$(find "$RESULTS" -type f | wc -l)
echo "kball: sending $NbFiles files ($(du -sh "$RESULTS" | cut -f1)) from $RESULTS" >&2

# 4. Archive on stdout; the names of the files (tar -v, on stderr) become a '[i/N] file' progress on stderr
{{ tar -cvf - -C "$(dirname "$RESULTS")" "$(basename "$RESULTS")" 2>&1 1>&3 | \\
    awk -v N=$NbFiles '{{ if ($0 !~ /\\/$/) printf "[%d/%d] %s\\n", ++i, N, $0; else print; fflush() }}' >&2; }} 3>&1
'''
    # Unix line endings (the script runs on Linux even if written on Windows), and executable
    ScriptPath = os.path.join(OutputFolder, 'fetch_results.sh')
    with open(ScriptPath, 'w', newline='\n') as File:
        File.write(Script)
    os.chmod(ScriptPath, 0o755)

    return ScriptPath
