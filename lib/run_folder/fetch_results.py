"""Script run on the remote computer that sends the results of a simulation to the local computer."""
import os
from pathlib import PurePosixPath

from lib.run_folder.watchdog import NORMAL_END_TEXT


def write_fetch_results_script(OutputFolder, Config, MitgcmResultsFolder):
    """
    Write fetch_results.sh at the root of the simulation folder. 'Fetch results from kball_laken.bat' (local Windows
    computer) sends its local copy to kball and runs it through ssh, so kball always runs the latest version:
      'ssh <host> "bash -s -- [force] [missing]" < fetch_results.sh[+ list of the local files] | tar -xf -'
    (it can also be run on kball: 'bash <RemoteRoot>/2-preprocessing-outputs/<sim>/fetch_results.sh [force]').
    The script writes a tar archive to stdout; messages and a progress bar (bytes sent) go to stderr, so they are shown in
    the local terminal without mixing with the archive:
      - MITgcm not launched or still running: nothing is sent (exit 1);
      - run without NORMAL_END_TEXT in STDOUT.0000 and no 'force' argument: the archive only holds '<sim>.download_refused.txt' (reason
        and end of the logs), which the .bat shows before asking whether to download anyway;
      - finished run, or 'force': the logs of the run are copied to <results>/logs/ and the whole results folder is
        sent, with the marker download_check.txt ('NORMAL END' or 'FAILED RUN (forced download)') as the last
        file of the archive, so it is only extracted once everything else is;
      - 'missing': the rest of stdin (after the script) holds the list of the files already on the local computer
        ('<size><TAB><path relative to the results folder>' lines, written by the .bat); only the other files, and those of a different size (cut
        by an interrupted download), are sent, plus the marker.
    Inputs:
      OutputFolder (str)        - simulation folder
      Config (ConfigObject)     - run settings (RemoteRoot, SimulationName)
      MitgcmResultsFolder (str) - absolute results folder on the remote computer
    Output:
      (str) - path of the written script
    """
    SimDir = PurePosixPath(Config.RemoteRoot) / '2-preprocessing-outputs' / Config.SimulationName
    Script = f'''#!/bin/bash
# Sends the results of the MITgcm simulation '{Config.SimulationName}' as a tar archive on stdout.
# Written by MAIN_preprocessing.ipynb; 'Fetch results from kball_laken.bat' sends its local copy and runs it:
#   ssh <host> "bash -s -- [force] [missing]" < fetch_results.sh | tar -xf -
# (or on kball: bash {SimDir}/fetch_results.sh [force])
# Without 'force', a run that did not end properly only sends {Config.SimulationName}.download_refused.txt.
# With 'missing', only the files not listed on stdin after the script ('<size><TAB><path>', the files already
# downloaded) are sent.
# All messages go to stderr (stdout carries the archive only).
# The whole script is one {{ }} block: bash reads all of it before running it, so with 'bash -s' the rest of stdin
# (the list of the local files) is left to the script instead of being read as commands
{{
set -o pipefail
SIM="{Config.SimulationName}"
# Absolute: the .bat sends the local copy of this script through ssh ('bash -s'), so it has no folder of its own
SIM_DIR="{SimDir}"
# Arguments, in any order: 'force' (download a failed run), 'missing' (only the files not downloaded yet)
FORCE=""; MISSING=""
for Arg in "$@"; do
  case "$Arg" in force) FORCE=force ;; missing) MISSING=1 ;; esac
done
refuse() {{ echo "kball: download refused: $1" >&2; exit 1; }}

# 1. Checks: launched, not running anymore
cd "$SIM_DIR/run" 2> /dev/null || refuse "the simulation was not launched (no run folder)"
if [ -f mitgcm.pid ] && kill -0 "$(cat mitgcm.pid)" 2> /dev/null; then
  refuse "the simulation is still running (bash $SIM_DIR/progress.sh on kball to follow it)"
fi

# 2. Finished properly? If not, and no 'force': send only a report (reason + end of the logs) for the .bat to show
if grep -q "{NORMAL_END_TEXT}" STDOUT.0000 2> /dev/null; then
  Status="NORMAL END"
elif [ "$FORCE" = force ]; then
  Status="FAILED RUN (forced download)"
  echo "kball: the simulation did not finish properly, sending the results and logs anyway" >&2
else
  echo "kball: the simulation did not finish properly (no '{NORMAL_END_TEXT}' in run/STDOUT.0000)" >&2
  Report="$(mktemp -d)"
  {{
    echo "The simulation $SIM did not finish properly: no '{NORMAL_END_TEXT}' in run/STDOUT.0000."
    echo "Last model time: $(awk '$3=="%MON" && $4=="time_secondsf" {{T=$6}} END {{print T}}' STDOUT.0000 2> /dev/null) s"
    for File in run/STDERR.0000 run/output_$SIM.out run/watchdog.log launch.log; do
      [ -s "../$File" ] && {{ echo; echo "=== Last lines of $File ==="; tail -n 15 "../$File"; }}
    done
  }} > "$Report/$SIM.download_refused.txt"
  tar -cf - -C "$Report" "$SIM.download_refused.txt"
  rm -rf "$Report"
  exit 0
fi
RESULTS="$(cd "{MitgcmResultsFolder}" 2> /dev/null && pwd)" || refuse "no results folder {MitgcmResultsFolder}"

# 3. Logs of the run, sent with the results (to understand a failed run locally): MITgcm logs of the first core,
# non-empty error logs of all cores, mpirun and watchdog messages, launch log, run parameters
mkdir -p "$RESULTS/logs"
cp STDOUT.0000 output_$SIM.out watchdog.log ../launch.log "$RESULTS/logs/" 2> /dev/null
find . -maxdepth 1 -name 'STDERR.*' -size +0 -exec cp {{}} "$RESULTS/logs/" \\;
cp ../run_config/data* "$RESULTS/logs/" 2> /dev/null

# 4. Marker included in the archive: the .bat deletes its local copy before downloading and checks it is back,
# so an old local copy is never taken for a successful download; it also says whether the run failed
printf '%s\\n%s\\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$Status" > "$RESULTS/download_check.txt"

# 5. Files to send ('<size><TAB><path>' lines): all the files of the results folder or, with 'missing', those that
# are not in the local list (stdin) with the same size. The marker goes last, so it is only extracted once
# everything else is (its presence then means a complete download)
Tmp="$(mktemp -d)"
trap 'rm -rf "$Tmp"' EXIT
if [ -n "$MISSING" ]; then tr -d '\\r' > "$Tmp/local.txt"; else : > "$Tmp/local.txt"; fi
find "$RESULTS" -type f ! -path "$RESULTS/download_check.txt" -printf '%s\\t%P\\n' > "$Tmp/remote.txt"
awk -F'\\t' 'FILENAME == ARGV[1] {{ Have[$2] = $1; next }} !($2 in Have) || Have[$2] != $1' \\
  "$Tmp/local.txt" "$Tmp/remote.txt" > "$Tmp/send.txt"
printf '%s\\t%s\\n' "$(stat -c %s "$RESULTS/download_check.txt")" download_check.txt >> "$Tmp/send.txt"
awk -F'\\t' -v Folder="$(basename "$RESULTS")" '{{ print Folder "/" $2 }}' "$Tmp/send.txt" > "$Tmp/names.txt"

# 6. Size of the download, in bytes of tar archive (each file: 512-byte header + content rounded up to 512 bytes)
NbFiles=$(wc -l < "$Tmp/send.txt")
TotalBytes=$(awk -F'\\t' '{{ T += 512 + int(($1 + 511) / 512) * 512 }} END {{ printf "%d", T + 1024 }}' "$Tmp/send.txt")
Size=$(awk -F'\\t' '{{ T += $1 }} END {{ printf "%.2f GB", T / 1e9 }}' "$Tmp/send.txt")
if [ -n "$MISSING" ]; then
  echo "kball: sending the $(( NbFiles - 1 )) files not downloaded yet, of $(wc -l < "$Tmp/remote.txt") ($Size, from $RESULTS)" >&2
else
  echo "kball: sending $NbFiles files ($Size) from $RESULTS" >&2
fi

# 7. Archive on stdout, through a progress bar on stderr (python3 on kball; without it, no bar), redrawn on one line
# every 0.5 s ('\r') and ended once the archive is sent
METER=$(cat << 'EOF'
import os, sys, time
Total, Done, Start, Last = max(int(sys.argv[1]), 1), 0, time.time(), 0.0
def show(Done, LineEnd=''):
    Elapsed = max(time.time() - Start, 1e-6)
    Speed = Done / Elapsed
    Fraction = min(Done / Total, 1.0)
    Left = (Total - Done) / Speed if Speed > 0 and Done < Total else 0
    Bar = '#' * int(30 * Fraction) + '-' * (30 - int(30 * Fraction))
    sys.stderr.write('\\r[%s] %5.1f%%  %.2f / %.2f GB  %5.1f MB/s  %3d:%02d left ' % (
        Bar, 100 * Fraction, Done / 1e9, Total / 1e9, Speed / 1e6, Left // 60, Left % 60) + LineEnd)
    sys.stderr.flush()
show(0)
while True:
    Chunk = os.read(0, 1 << 20)
    if not Chunk:
        break
    sys.stdout.buffer.write(Chunk)
    Done += len(Chunk)
    if time.time() - Last > 0.5:
        show(Done)
        Last = time.time()
sys.stdout.buffer.flush()
show(Total, '\\n')
EOF
)
if command -v python3 > /dev/null; then
  tar -cf - -C "$(dirname "$RESULTS")" -T "$Tmp/names.txt" | python3 -c "$METER" "$TotalBytes"
else
  echo "kball: no python3, so no progress bar" >&2
  tar -cf - -C "$(dirname "$RESULTS")" -T "$Tmp/names.txt"
fi
# End here (with the exit code of tar): with 'bash -s', what follows the script on stdin is data, not commands
exit
}}
'''
    # Unix line endings (the script runs on Linux even if written on Windows), and executable
    ScriptPath = os.path.join(OutputFolder, 'fetch_results.sh')
    with open(ScriptPath, 'w', newline='\n') as File:
        File.write(Script)
    os.chmod(ScriptPath, 0o755)

    return ScriptPath
