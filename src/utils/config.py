"""
Configuration file for CourtListener API project
"""

import getpass
import os
from pathlib import Path
from datetime import datetime

################################################################################
# SET CODE LOCATION -----------------------------------------------------------

_user = getpass.getuser()

if _user == "hl2266":
    if "dropbox" in os.getcwd().lower():
        BASE_DIR = Path(
            "C:/Users/hl2266/YLS Dropbox/Hannah Lu/shared/NEPA Court Cases (Internal)/"
        )
        CODE_DIR = BASE_DIR / "Code" / "NEPA_court_cases_internal"
        DATA_ROOT_DIR = BASE_DIR / "Data"
    elif "docker" in os.getcwd().lower():
        BASE_DIR = Path("C:/Users/hl2266/project_dockers/nepa")
        _DROPBOX_DIR = Path(
            "C:/Users/hl2266/YLS Dropbox/Hannah Lu/shared/NEPA Court Cases (Internal)/"
        )
        CODE_DIR = BASE_DIR / "Code" / "NEPA_court_cases_internal"
        DATA_ROOT_DIR = _DROPBOX_DIR / "Data"
    elif "pi_zdl3" in os.getcwd().lower():
        BASE_DIR = Path(
            "/nfs/roberts/project/pi_zdl3/shared/NEPA court case project")
        CODE_DIR = BASE_DIR / "Code" / "NEPA_court_cases_internal"
        DATA_ROOT_DIR = BASE_DIR / "Data"
    else:
        raise ValueError("Invalid location specified")
else:
    raise ValueError("Invalid location specified")

################################################################################
# DATA DIRECTORY --------------------------------------------------------------

# Raw and Intermediate data directories
RAW_DATA_DIR = DATA_ROOT_DIR / "Raw"
INTERMEDIATE_DATA_DIR = DATA_ROOT_DIR / "Intermediate"

# Raw data file paths
ADELGLICKS_RAW_PATH = RAW_DATA_DIR / "Adelman Glicksman/data/NEPA Lit Circuit WL Sample-Combo Supp-Coded Final 2001-15 2.7.24.xlsx"
ADELGLICKS_SHEET_NAME = "NEPA Circuit Data"
COURTLISTENER_RAW_DIR = RAW_DATA_DIR / "CourtListener"
JUDGES_OUTPUT_DIR = INTERMEDIATE_DATA_DIR / "Judges"

# Output paths for cleaned datasets
CLEANED_DATASETS_DIR = INTERMEDIATE_DATA_DIR / "Cleaned Datasets"
ADELGLICKS_CLEANED_PATH = CLEANED_DATASETS_DIR / "AdelGlicks.csv"
COURTLISTENER_CLUSTER_CLEANED_PATH = CLEANED_DATASETS_DIR / "CourtListener/cluster_metadata.csv"

MATCHING_DIR = INTERMEDIATE_DATA_DIR / "Docket Matching"
COURTLISTENER_AG_MATCH_STATS_PATH = MATCHING_DIR / "CL_AG_match_stats.txt"
COURTLISTENER_AG_MATCHING_PATH = MATCHING_DIR / "CL_AG_matching.csv"
COURTLISTENER_AG_MATCHING_SPLIT_PATH = MATCHING_DIR / "CL_AG_matched_val_test_assignments.csv"

# OUTCOME_ASSIGNMENTS_DIR = INTERMEDIATE_DATA_DIR / "Outcome Coding Assignments" # deprecated
FTR_ASSIGNMENTS_DIR = INTERMEDIATE_DATA_DIR / "Feature Classification Assignments"
AG_VAL_ASSIGNMENTS_PATH = FTR_ASSIGNMENTS_DIR / "AG_val.csv"
AG_TEST_ASSIGNMENTS_PATH = FTR_ASSIGNMENTS_DIR / "AG_test.csv"
CL_TRAIN_ASSIGNMENTS_PATH = FTR_ASSIGNMENTS_DIR / "CL_train.csv"

# OUTCOME_PREDICTIONS_DIR = INTERMEDIATE_DATA_DIR / "Outcome Coding Predictions" # deprecated
FTR_PREDICTIONS_DIR = INTERMEDIATE_DATA_DIR / "Feature Classification Predictions"
CL_TRAIN_PREDICTIONS_PATH = FTR_PREDICTIONS_DIR / "CL_train_predictions.csv"

LLM_OPINION_CLF_RAW_PATH = INTERMEDIATE_DATA_DIR / "gemini_output/opinions_20251219_110552_coding_20260102_165440/opinions_20251219_110552_coding_20260102_165440.csv"
LLM_OPINION_CLF_PATH = FTR_PREDICTIONS_DIR / "LLM_case_outcome_coding.csv"

LLM_JUDGES_CLF_RAW_PATH = INTERMEDIATE_DATA_DIR / "gemini_output/opinions_20251219_110552_judges_20260429_111513/opinions_20251219_110552_judges_20260429_111513.csv"
LLM_JUDGES_CLF_PATH = FTR_PREDICTIONS_DIR / "LLM_judge_coding.csv"

COURTLISTENER_METADATA_W_FTRS_PATH = FTR_PREDICTIONS_DIR / "courtlistener_metadata_w_extracted_features.csv"

# other misc file paths
USGOV_PL_PATH = INTERMEDIATE_DATA_DIR / "usgov_plaintiffs_MB_04022026.csv"

################################################################################

# Set global timestamp for use as file/run identifier
RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

################################################################################
# COURTLISTENER DOWNLOADS

RUN_DIR = COURTLISTENER_RAW_DIR / f"run_{RUN_TIMESTAMP}"
CURR_OPINIONS_DIR = RUN_DIR / "opinions"

# API Configuration
API_KEY_PATH = CODE_DIR / "secret" / "COURTLISTENER_API_KEY.txt"
with open(API_KEY_PATH) as f:
    API_KEY = f.read().strip()

BASE_PDF_URL = "https://storage.courtlistener.com"
BASE_API_URL = "https://www.courtlistener.com/api/rest/v4"

# API Settings
REQUEST_DELAY = 0.5  # seconds between requests (be nice to the API)
TIMEOUT = 60  # seconds
RETRY_WAIT_TIME = 5  # seconds to wait before retrying on retryable errors
MAX_RETRIES = 5  # maximum number of retries for 502 and 429 errors

################################################################################


def setup_directories():
    """Create project directory structure"""
    directories = [
        COURTLISTENER_RAW_DIR,
        RUN_DIR,
        CURR_OPINIONS_DIR,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    # Initialize global logger
    from src.utils.logger import Logger, set_logger
    logger = Logger(log_dir=RUN_DIR)
    set_logger(logger)
    logger.info("Logger initialized", run_dir=str(RUN_DIR))
