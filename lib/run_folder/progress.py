"""Progress bar of the simulation, shown on the remote computer."""
import os


def write_progress_script(OutputFolder, Config, MitgcmResultsFolder, StartTimeInSecond, EndTimeInSecond):
    """
    Write progress.sh at the root of the simulation folder. launch_simulation.sh runs it at the end, and it can be
    run again at any time ('bash <simulation folder>/progress.sh'; Ctrl+C only stops the display, not MITgcm).
    The progress is the iteration number of the latest result file 3Dsnaps.<iteration>.data (written every model
    hour); the time left is extrapolated from the times at which the first and latest result files were written.
    Inputs:
      OutputFolder (str)        - simulation folder
      Config (ConfigObject)     - run settings (SimulationName, TimeStep [s])
      MitgcmResultsFolder (str) - results folder on the remote computer, absolute or relative to run/
      StartTimeInSecond (float) - start of the simulation, in seconds from the reference date
      EndTimeInSecond (float)   - end of the simulation, in seconds from the reference date
    Output:
      (str) - path of the written script
    """
    # Iterations of the first and last time step (MITgcm numbers the files with the iteration number)
    StartIter = int(round(StartTimeInSecond / Config.TimeStep))
    EndIter = int(round(EndTimeInSecond / Config.TimeStep))

    Script = f'''#!/bin/bash
# Progress bar of the MITgcm simulation '{Config.SimulationName}' (written by MAIN_preprocessing.ipynb).
# Run from anywhere: bash <simulation folder>/progress.sh    (Ctrl+C stops the display, not the simulation)
SIM_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
cd "$SIM_DIR/run" || {{ echo "No run folder: the simulation was not launched"; exit 1; }}
RESULTS="{MitgcmResultsFolder}/outputs"
START_ITER={StartIter}
END_ITER={EndIter}
DT={Config.TimeStep}
trap 'echo; echo "Display stopped, the simulation continues (bash $SIM_DIR/progress.sh to show it again)"; exit 0' INT

# Duration in seconds -> '2d03h', '5h12m' or '7m'
format_time() {{
  local S=$1
  if [ "$S" -ge 86400 ]; then printf '%dd%02dh' $((S / 86400)) $((S % 86400 / 3600))
  elif [ "$S" -ge 3600 ]; then printf '%dh%02dm' $((S / 3600)) $((S % 3600 / 60))
  else printf '%dm' $((S / 60)); fi
}}

# Is MITgcm running? (PID written by launch_simulation.sh)
is_running() {{ [ -f mitgcm.pid ] && kill -0 "$(cat mitgcm.pid)" 2> /dev/null; }}

while true; do
  # Iterations of the first and latest result files, and the times at which they were written
  Iters="$(ls "$RESULTS" 2> /dev/null | sed -n 's/^3Dsnaps\\.\\([0-9]*\\)\\.data$/\\1/p' | sort -n)"
  FirstIter="$(echo "$Iters" | head -n 1)"; LastIter="$(echo "$Iters" | tail -n 1)"
  Iter=$((10#${{LastIter:-$START_ITER}}))

  # Time left: (iterations left) x (wall time per iteration between the first and latest files)
  Eta="..."
  if [ -n "$FirstIter" ] && [ "$FirstIter" != "$LastIter" ]; then
    T1=$(stat -c %Y "$RESULTS/3Dsnaps.$FirstIter.data"); T2=$(stat -c %Y "$RESULTS/3Dsnaps.$LastIter.data")
    Left=$(( (END_ITER - Iter) * (T2 - T1) / (Iter - 10#$FirstIter) - ($(date +%s) - T2) ))
    Eta="$(format_time $(( Left > 0 ? Left : 0 )))"
  fi

  # Bar of 40 characters, percentage and model days done / total
  awk -v I=$Iter -v S=$START_ITER -v E=$END_ITER -v DT=$DT -v ETA="$Eta" 'BEGIN {{
    F = (I - S) / (E - S); if (F < 0) F = 0; if (F > 1) F = 1; N = int(F * 40 + 0.5)
    Bar = ""; for (k = 1; k <= 40; k++) Bar = Bar (k <= N ? "#" : "-")
    printf "\\r[%s] %5.1f%%  model day %.1f / %.1f  time left %s   ", Bar, 100 * F, (I - S) * DT / 86400, (E - S) * DT / 86400, ETA
  }}'

  is_running || break
  sleep 10
done

# MITgcm has stopped: properly or not
echo
if grep -q "NORMAL END" STDOUT.0000 2> /dev/null; then
  echo "Simulation finished (NORMAL END). Results: $(cd "$RESULTS" 2> /dev/null && pwd)"
else
  echo "MITgcm is not running and did not finish properly: see $SIM_DIR/run/STDERR.0000 and watchdog.log"
fi
'''
    # Unix line endings (the script runs on Linux even if written on Windows), and executable
    ScriptPath = os.path.join(OutputFolder, 'progress.sh')
    with open(ScriptPath, 'w', newline='\n') as File:
        File.write(Script)
    os.chmod(ScriptPath, 0o755)

    return ScriptPath
