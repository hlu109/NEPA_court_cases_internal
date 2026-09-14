#!/bin/bash
#SBATCH --partition=week
#SBATCH --job-name=gemini_extraction
#SBATCH --output="/nfs/roberts/project/pi_zdl3/shared/NEPA court case project/slurm_logs/gemini_extraction_%j.log"
#
#SBATCH --time=3-00:00:00
#SBATCH --mem=50G
#SBATCH --ntasks=1
#
#SBATCH --mail-type=FAIL,END
date
cd "/nfs/roberts/project/pi_zdl3/shared/NEPA court case project/Code/NEPA_court_cases_internal"

module load Python
source venv/bin/activate

python src/01_data/02_gemini_extraction/01_main.py
