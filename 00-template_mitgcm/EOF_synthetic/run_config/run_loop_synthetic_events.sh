#!/bin/bash -l

# Script to run the synthetic events in one go
export $(cat my_env.txt | xargs)

OUTPUT_DIR="../outputs"
# Number of MPI processes (Px * Py of code/SIZE.h), e.g. NB_CORES=33 bash run_loop_synthetic_events.sh
NB_CORES=${NB_CORES:?set NB_CORES to the number of cores}

# Correct Bash array syntax
DATES=(
"2025-04-07" "2025-04-22"
"2025-05-07" "2025-05-22" "2025-06-07" "2025-06-22"
"2025-07-07" "2025-07-22" "2025-08-07" "2025-08-22"
"2025-09-07" "2025-09-22" "2025-10-07" "2025-10-22"
"2025-11-07" "2025-11-22" "2025-12-07"
)

NLOOPS=${#DATES[@]}

for (( i=0; i<NLOOPS; i++ ))
do
    date=${DATES[$i]}
    
    echo "=== Starting loop ${date} at $(date '+%Y-%m-%d %H:%M:%S') ==="
    echo "Creating directories in ${OUTPUT_DIR}"
    
    mkdir -p "${OUTPUT_DIR}/outputs_${date}"
    
    rm -rf "${OUTPUT_DIR}/to_delete"
    mkdir -p "${OUTPUT_DIR}/to_delete"
    
    echo "Cleaning up run directory"
    rm -f ../run/*
    ln -s ../run_config/* .
    cp ../build/mitgcmuv .
    
    echo "Update tRef with stratification"
    python ./fetch_initial_stratification.py "${date}" || {
        echo "fetch_initial_stratification.py failed at loop $i"
        exit 1
    }
    
    echo "Change output folder name in data.diagnostics"
    sed -i "s|fileName.*=.*|fileName(1) = '${OUTPUT_DIR}/outputs_${date}/3Dsnaps',|" data.diagnostics
    
    echo "=== Loop ${date}: Starting MITgcm at $(date '+%Y-%m-%d %H:%M:%S') ==="
    mpirun -np "${NB_CORES}" ./mitgcmuv || {
        echo "MITgcm failed at loop $i"
        exit 1
    }
done