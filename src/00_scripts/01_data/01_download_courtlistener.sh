#!/bin/bash
#SBATCH --partition=day
#SBATCH --job-name=download_courtlistener
#SBATCH --output="/nfs/roberts/project/pi_zdl3/shared/NEPA court case project/slurm_logs/download_courtlistener_%j.log"
#
#SBATCH --time=23:59:00
#SBATCH --mem=100G
#SBATCH --ntasks=1
#
#SBATCH --mail-type=FAIL,END
date
cd "/nfs/roberts/project/pi_zdl3/shared/NEPA court case project/Code/NEPA_court_cases_external"

module load Python
source venv/bin/activate

python 01_data/01_download_courtlistener/main.py