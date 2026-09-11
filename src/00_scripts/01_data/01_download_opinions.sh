#!/bin/bash
#SBATCH --partition=day
#SBATCH --job-name=download_opinions
#SBATCH --output="/nfs/roberts/project/pi_zdl3/shared/NEPA court case project/slurm_logs/download_opinions_%j.log"
#
#SBATCH --time=5:00:00
#SBATCH --mem=5G
#SBATCH --ntasks=1
#
#SBATCH --mail-type=FAIL,END
date
cd "/nfs/roberts/project/pi_zdl3/shared/NEPA court case project/Code/NEPA_court_cases_internal"

module load Python
source venv/bin/activate

python src/01_data/01_download_courtlistener/download_opinions.py
