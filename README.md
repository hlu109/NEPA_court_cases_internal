# NEPA Court Cases

This repository contains code for downloading, processing, and analyzing appellate court cases related to the National Environmental Policy Act (NEPA). Bulk cases are downloaded via the CourtListener API, coded using the Gemini API, and evaluated against external "ground-truth" data. 

## Project Structure

```
NEPA_court_cases/
├── src/
│   ├── 01_data/                        # Bulk case download from CourtListener (run main.py)
│   ├── 02_coding_cases/                # LLM-based case classification (run main.py)
│   ├── 03_clean_merge_split_cases.py   # Merge CourtListener and external data source for subsequent performance eval
│   ├── 04_eval.py                      # Evaluate LLM coding performance
│   ├── 05_summary_stats.py             # Summary statistics generation
│   └── utils/                          # Catch-all for util functions
│       ├── api_utils.py               
│       ├── config.py                   # User must edit according to local machine
│       ├── courtlistener_utils.py     
│       └── logger.py                  
└── secret/                             # User must create this folder (hidden from git)
    ├── COURTLISTENER_API_KEY.txt
    └── GEMINI_API_KEY.txt
```

Each of the scripts (03-05) contain a main function (which will eventually be sourced by a master script in the root for reproducibility). 

## Data Directory

The project uses a separate data directory (outside the code repository) with the following structure:
- `Data/Raw/`: Raw data, including CourtListener, AdelGlicks, and Breakthrough
- `Data/Intermediate/`: Intermediate/processed datasets, including cleaned and merged data


## Setup
- Recommended: create a python virtual environment (e.g. via `virtualenv`).
- Install dependencies.
   ```
   pip install -r requirements.txt
   ```
- Configure paths in `src/utils/config.py` to match local setup.
- To run code in `01_data/` and `02_coding_cases/`, you'll need a personal API key for CourtListener and Google Cloud/Google Gemini respectively. The API key should be stored in `secret/COURTLISTENER_API_KEY.txt` and `secret/GEMINI_API_KEY.txt`. They are omitted from git version control as they should be treated like passcodes. 



## Gemini 
PLACEHOLDER 
* insert instructions on API keys. 


### Gemini Running Logistics
For the judge-only extraction, Gemini took around 7 hours and cost ~$24 for a roughly 1k sample using the 2.5 flash model. After fixing the sample (now ~3x) and merging the outcome coding together with the judge name extraction, I'm estimating a cost of $75-150 and a runtime of 21-42 hours. 
