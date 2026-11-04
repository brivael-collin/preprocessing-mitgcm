#!/bin/bash -l

#SBATCH --account=em09
#SBATCH --job-name="MITgcmInference"
#SBATCH --time=!time!
#SBATCH --ntasks=929
#SBATCH --cpus-per-task=1
#SBATCH --partition=normal
#SBATCH --mail-user=anne.leroquais@eawag.ch
#SBATCH --mail-type=end
# Script to run the simulation on the CSSC cluster

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK}
export MPICH_GPU_SUPPORT_ENABLED=0
source ~/eiger_venv/bin/activate

mkdir -p ../outputs
mkdir -p ../to_delete

srun --ntasks=${SLURM_NTASKS} ./mitgcmuv

python extract_sta_results.py
python extract_surface_results.py