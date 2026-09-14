import os
from datetime import datetime
from data_structs.Case import Case
from utils.config import DATA_ROOT_DIR, CODE_DIR

# TODO: merge this config with the main config in utils/config.py

# ------------------------------------------------------------------------------
# SET PARAMETERS
# ------------------------------------------------------------------------------

# Optional note to log purpose of the run
NOTE = None

# Set API Parameters -------------------------------------------
# Define the model you are going to use (flash is free with 1,500 requests per day)
# gemini_model_id = "gemini-2.0-flash"
gemini_model_id = "gemini-2.5-flash"
# gemini_model_id = "gemini-2.5-pro"
# gemini_model_id = "gemini-3-flash-preview"
# gemini_model_id = "gemini-3-pro-preview"

# SET GEMINI PROMPT ------------------------------------------------------------
# Indicate the file name for the prompt to use
prompt_text_name = "case_prompt.txt"

# SET RESUME PARAMETERS ---------------------------------------------------------
REUSE_OLD_RESULTS = True
RESUME_RUN_IDENTIFIER = "gemini_20260914_114005"

# SET FILE PATHS -------------------------------------------
# Set input directory run identifier
INPUT_RUN_IDENTIFIER = "run_20260910_184612"

# SET OUTPUT PATH  -------------------------------------------------------------
OUTPUT_DIR = DATA_ROOT_DIR / "Intermediate"

# Set Case Schema -----------------------------------
page_schema = Case

# Case Parameters -------------------------------------------
# Case filtering (optional) - if None, processes all cases in INPUT_DIR
# Example: ["10033657", "1027273"] to process specific cases
case_ids = None
# case_ids = ["5738", "2471"]

# ------------------------------------------------------------------------------
# AUTO SET REMAINING FILE PATHS
# ------------------------------------------------------------------------------

# save each execution with a separate file suffix --- to ensure nothing is over-written
# TODO: refactor to use the generate timestamp function already in utils
if REUSE_OLD_RESULTS:
    if not RESUME_RUN_IDENTIFIER:
        raise ValueError(
            "REUSE_OLD_RESULTS is True but RESUME_RUN_IDENTIFIER is not set.")
    # reuse the prior run's identifier so intermediate JSONs, the output CSV, and the log file all resolve to the resumed run's paths
    identifier = RESUME_RUN_IDENTIFIER
else:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    identifier = "gemini_" + timestamp

INPUT_DIR = DATA_ROOT_DIR / "Raw" / "CourtListener" / INPUT_RUN_IDENTIFIER / "opinions"

prompt_text_path = CODE_DIR / "src" / "01_data" / "02_gemini_extraction" / "prompts" / prompt_text_name

gemini_dir = OUTPUT_DIR / "gemini_output"
log_dir = OUTPUT_DIR / "gemini_logs"

OUTPUT_FILE_NAME = INPUT_RUN_IDENTIFIER + "_" + identifier + ".csv"

# folder for intermediate results
results_dir = gemini_dir / (INPUT_RUN_IDENTIFIER + "_" + identifier)
temp_dir = results_dir / "temp"
