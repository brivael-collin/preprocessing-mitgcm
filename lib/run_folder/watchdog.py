"""Watchdog script that follows the simulation on the remote computer and sends an email when it ends."""
import os

# Name of the local download script (code/misc/kball-transfer/, copied by the user to the Desktop), quoted in the emails
FETCH_BAT_NAME = 'Fetch results from kball_laken.bat'

# Line that MITgcm writes at the end of STDOUT.0000 when the run ends without error (eesupp/src/main.F). The words
# 'NORMAL END' do not appear there: they come from Fortran's STOP 'NORMAL END', printed to the mpirun output
NORMAL_END_TEXT = 'PROGRAM MAIN: Execution ended Normally'


def write_watchdog_script(OutputFolder, Config, MitgcmResultsFolder):
    """
    Write watchdog.sh at the root of the simulation folder. launch_simulation.sh starts it in run/ next to MITgcm.
    Every CheckInterval seconds it reads the monitor statistics that MITgcm writes to STDOUT.0000 (every MonitorFreq
    model seconds). It sends an email when it starts (to check that emails arrive). If a value is NaN/Inf or out of
    the Limits, it stops the run (kills mpirun) and sends an email.
    When mpirun ends, it sends an email saying whether the run finished properly (NORMAL_END_TEXT in STDOUT.0000)
    or failed, with the
    end of the log files. Emails use the 'mail' command of the remote computer; whether 'mail' accepted each one is
    written to run/watchdog.log (without NotifyEmail or 'mail', the messages are only written there).
    Inputs:
      OutputFolder (str)        - simulation folder
      Config (ConfigObject)     - run settings (SimulationName, ComputerName, Watchdog: NotifyEmail, CheckInterval,
                                  Limits with ThetaMin/Max [degC], SaltMin/Max [psu], UVelMax and WVelMax [m/s], CflMax)
      MitgcmResultsFolder (str) - absolute results folder on the remote computer
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

# Send an email (subject $1, body $2) and log whether 'mail' accepted it; only logged if no address or no 'mail'
notify() {{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
  if [ -z "$EMAIL" ] || ! command -v mail > /dev/null; then
    echo "(no email sent: NotifyEmail empty in config.json or no 'mail' command on $(hostname))"; printf '%s\\n' "$2"
  elif printf '%s\\n' "$2" | mail -s "[MITgcm $SIM] $1" "$EMAIL"; then
    echo "Email handed to mail for $EMAIL (not received = mail is not delivered from $(hostname): check spam,"
    echo "  then the mail setup of $(hostname) with: echo test | mail -s test $EMAIL)"
  else
    echo "Email NOT sent: mail failed (exit $?)"; printf '%s\\n' "$2"
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

# 0. Email at start: shows right away whether the emails of this computer reach NotifyEmail
notify "started" "MITgcm started on $(hostname) (mpirun PID $PID), simulation folder $(dirname "$(pwd)").
Results: $RESULTS
Another email follows when the run finishes, fails or is stopped by this watchdog."

# 1. While MITgcm runs: check the statistics, stop the run at the first unrealistic value
while kill -0 "$PID" 2> /dev/null; do
  sleep "$INTERVAL"
  Problem="$(check_values)"
  if [ -n "$Problem" ]; then
    kill "$PID" 2> /dev/null; sleep 30; kill -9 "$PID" 2> /dev/null
    notify "STOPPED: unrealistic values" "The watchdog stopped the run: $Problem
Limits (config.json, ComputerConfig.Watchdog.Limits): {Limits}
Results and logs can still be downloaded with '{FETCH_BAT_NAME}' (answer Y to 'Download anyway?').

$(summary)"
    exit 1
  fi
done

# 2. MITgcm has ended: properly or not
if grep -q "{NORMAL_END_TEXT}" STDOUT.0000 2> /dev/null; then
  notify "finished" "To download the results, double-click '{FETCH_BAT_NAME}' on your Desktop and choose $SIM.

$(summary)"
else
  notify "FAILED (no NORMAL END)" "MITgcm stopped before the end (error, or killed by hand): no '{NORMAL_END_TEXT}'
at the end of run/STDOUT.0000.
To download the results and logs anyway, double-click '{FETCH_BAT_NAME}' on your Desktop, choose $SIM and
answer Y to 'Download anyway?'.

$(summary)"
fi
'''
    # Unix line endings (the script runs on Linux even if written on Windows), and executable
    ScriptPath = os.path.join(OutputFolder, 'watchdog.sh')
    with open(ScriptPath, 'w', newline='\n') as File:
        File.write(Script)
    os.chmod(ScriptPath, 0o755)

    return ScriptPath
