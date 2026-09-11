#!/bin/bash

#SBATCH --job-name=bin_tracts
#SBATCH --account=eda_ceds
#SBATCH --partition=bdwall  # bdwall runtime, bdws testing
#SBATCH --nodes=1  # Adjust the number of nodes
#SBATCH --ntasks-per-node=1  # Adjust the number of tasks per node
#SBATCH --array=1-22 # If you want to run 1296 tasks
#SBATCH --time=03:00:00
#SBATCH --output=log/bin_tracts.out  # Standard output
#SBATCH --error=log/bin_tracts.err   # Standard error

# Setup My Environment
module load anaconda3
source activate env_cria

# Run the storm model
srun ./run_model.sh