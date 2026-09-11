#!/bin/bash
# Compute start and end index for each task
TASK_ID=$SLURM_ARRAY_TASK_ID  # This is automatically set for each array job

idx_column=$TASK_ID

# Run your Python script
python -m task_script --idx_column $idx_column --run_test True