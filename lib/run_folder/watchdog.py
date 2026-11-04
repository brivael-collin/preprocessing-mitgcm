"""Watchdog script that follows the simulation on the remote computer and sends an email when it ends."""
import os

# Name of the local download script (code/kball-transfer/, copied by the user to the Desktop), quoted in the emails
FETCH_BAT_NAME = 'Fetch results from kball_laken.bat'


def write_watchdog_script(OutputFolder, Config, MitgcmResultsFolder):
    """
    Write watchdog.sh at the root of the simulation folder. launch_simulation.sh starts it in run/ next to MITgcm.
    Every CheckInterval seconds it reads the monitor statistics that MITgcm writes to STDOUT.0000 (every MonitorFreq
    model seconds). If a value is NaN/Inf or out of the Limits, it stops the run (kills mpirun) and sends an email.
    When mpirun ends, it sends an email saying whether the run finished properly ('NORMAL END') or failed, with the
    end of the log files. Emails use the 'mail' command of the remote computer; without NotifyEmail they are only
    written to run/watchdog.log.
    Inputs:
      OutputFolder (str)        - simulation folder
      Config (ConfigObject)     - run settings (SimulationName, ComputerName, Watchdog: NotifyEmail, CheckInterval,
                                  Limits with ThetaMin/Max [degC], SaltMin/Max [psu], UVelMax and WVelMax [m/s], CflMax)
      MitgcmResultsFolder (str) - results folder on the remote computer, absolute or relative to run/
    Output:
      (str) - path of the written script
    """
    Watchdog = Config.Watchdog
    Limits = Watchdog['Limits']
    Script = f'''#!/bin/bash
# Watchdog of the MITgcm simulation '{Config.SimulationName}' on '{Config.ComputerName}'.
# Written by MAIN_preprocessing.ipynb; started in run/ by launch_simulation.sh: bash ../watchdog.sh <mpirun PID>
# Stops the run if the model statistics (STDOUT.0000) are NaN or unrealistic, and sends an email when the run ends.
PID="$1"
EMAIL="{Watchdog['NotifyEmail']}"
INTERVAL={Watchdog['CheckInterval']}
SIM="{Config.SimulationName}"
RESULTS="{MitgcmResultsFolder}/outputs"
START="$(date '+%Y-%m-%d %H:%M')"

# Send an email (subject $1, body $2), or only log it if no address or no 'mail' command
notify() {{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
  if [ -n "$EMAIL" ] && command -v mail > /dev/null; then
    printf '%s\\n' "$2" | mail -s "[MITgcm $SIM] $1" "$EMAIL"
  else
    echo "(no email sent: NotifyEmail empty in config.json or no 'mail' command)"; printf '%s\\n' "$2"
  fi
}}

# Summary of the run for the emails: dates, last model time, number of result files, end of the log files
summary() {{
  echo "Simulation: $SIM ($(pwd))"
  echo "Started: $START, ended: $(date '+%Y-%m-%d %H:%M')"
  echo "Last model time: $(awk '$3=="%MON" && $4=="time_secondsf" {{T=$6}} END {{print T}}' STDOUT.0000 2>/dev/null) s"
  echo "Result files in $RESULTS: $(ls "$RESULTS" 2>/dev/null | grep -c '^3Dsnaps.*data$')"
  for File in STDERR.0000 output_$SIM.out STDOUT.0000; do
    [ -s "$File" ] && {{ echo; echo "=== Last lines of $File ==="; tail -n 20 "$File"; }}
  done
}}

# First NaN/Inf or out-of-range monitor value of STDOUT.0000 (lines '%MON <name> = <value>'), empty if none
check_values() {{
  [ -f STDOUT.0000 ] || return 0
  awk -v TMIN={Limits['ThetaMin']} -v TMAX={Limits['ThetaMax']} -v SMIN={Limits['SaltMin']} -v SMAX={Limits['SaltMax']} \\
      -v UMAX={Limits['UVelMax']} -v WMAX={Limits['WVelMax']} -v CMAX={Limits['CflMax']} '
    $3 == "%MON" {{
      Name = $4; Value = $6; X = Value + 0
      if (Name == "time_secondsf") Time = Value
      Bad = (tolower(Value) ~ /nan|inf|\\*/)
      if (Name == "dynstat_theta_min" && X < TMIN) Bad = 1
      if (Name == "dynstat_theta_max" && X > TMAX) Bad = 1
      if (Name == "dynstat_salt_min"  && X < SMIN) Bad = 1
      if (Name == "dynstat_salt_max"  && X > SMAX) Bad = 1
      if (Name ~ /^dynstat_[uv]vel_(max|min)$/ && (X > UMAX || -X > UMAX)) Bad = 1
      if (Name ~ /^dynstat_wvel_(max|min)$/    && (X > WMAX || -X > WMAX)) Bad = 1
      if (Name ~ /^advcfl_.*_max$/ && X > CMAX) Bad = 1
      if (Bad) {{ print Name " = " Value " at model time " Time " s"; exit }}
    }}' STDOUT.0000
}}

echo "Watchdog started for mpirun PID $PID (check every $INTERVAL s, email: ${{EMAIL:-none}})"

# 1. While MITgcm runs: check the statistics, stop the run at the first unrealistic value
while kill -0 "$PID" 2> /dev/null; do
  sleep "$INTERVAL"
  Problem="$(check_values)"
  if [ -n "$Problem" ]; then
    kill "$PID" 2> /dev/null; sleep 30; kill -9 "$PID" 2> /dev/null
    notify "STOPPED: unrealistic values" "The watchdog stopped the run: $Problem
Limits (config.json, ComputerConfig.Watchdog.Limits): {Limits}

$(summary)"
    exit 1
  fi
done

# 2. MITgcm has ended: properly or not
if grep -q "NORMAL END" STDOUT.0000 2> /dev/null; then
  notify "finished" "To download the results, double-click '{FETCH_BAT_NAME}' on your Desktop and choose $SIM.

$(summary)"
else
  notify "FAILED (no NORMAL END)" "MITgcm stopped before the end (error, or killed by hand).

$(summary)"
fi
'''
    # Unix line endings (the script runs on Linux even if written on Windows), and executable
    ScriptPath = os.path.join(OutputFolder, 'watchdog.sh')
    with open(ScriptPath, 'w', newline='\n') as File:
        File.write(Script)
    os.chmod(ScriptPath, 0o755)

    return ScriptPath
