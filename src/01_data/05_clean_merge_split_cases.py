"""
Clean court case datasets, harmonize variable codings, and match cases by their docket number sets. Assign validation/test splits for matched cases and save train/val/test files.
"""

import csv
import re
from typing import List
# from sklearn.model_selection import train_test_split
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add project root to Python path to allow imports from src.utils
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


from utils.config import (
    INTERMEDIATE_DATA_DIR,
    ADELGLICKS_RAW_PATH, 
    ADELGLICKS_SHEET_NAME, 
    ADELGLICKS_CLEANED_PATH,
    COURTLISTENER_CLUSTER_CLEANED_PATH,
    COURTLISTENER_AG_MATCH_STATS_PATH,
    COURTLISTENER_AG_MATCHING_PATH,
    COURTLISTENER_AG_MATCHING_SPLIT_PATH,
    FTR_ASSIGNMENTS_DIR,
    AG_VAL_ASSIGNMENTS_PATH,
    AG_TEST_ASSIGNMENTS_PATH,
    CL_TRAIN_ASSIGNMENTS_PATH,
    COURTLISTENER_RAW_DIR,
    LLM_OPINION_CLF_RAW_PATH,
    LLM_OPINION_CLF_PATH,
    LLM_JUDGES_CLF_RAW_PATH,
    LLM_JUDGES_CLF_PATH,
    CL_TRAIN_PREDICTIONS_PATH,
    COURTLISTENER_METADATA_W_FTRS_PATH,
    USGOV_PL_PATH
)


def _normalize_dash_characters(text: str) -> str:
    """
    Normalize all dash/hyphen variants (en dash, em dash, figure dash, minus 
    sign, encoding issues, etc.) to a standard hyphen-minus (-) for consistency
    across datasets.

    Args:
        text: String that may contain various dash characters

    Returns:
        String with all dash characters normalized to standard hyphen
    """
    if pd.isna(text):
        return text

    text = str(text)

    # Common dash/hyphen variants to normalize:
    dash_variants = [
        '–',  # En dash (U+2013)
        '—',  # Em dash (U+2014)
        '‒',  # Figure dash (U+2012)
        '−',  # Minus sign (U+2212)
        '‑',  # Non-breaking hyphen (U+2011)
        'â€"',  # Encoding corruption (Windows-1252)
    ]

    for dash in dash_variants:
        text = text.replace(dash, '-')

    return text


def _standardize_judge_string(judge_series: pd.Series) -> pd.Series:
    """ 
    Standardize judge text.
    """
    judge_string = judge_series.fillna("").astype(str).str.strip().str.upper()
    return judge_string
    

def _extract_last_name(name: str) -> str:
    name = str(name).strip()
    if not name:
        return ""
    suffixes = {"JR", "SR", "II", "III", "IV", "V"}
    last_name = ""
    # handle "last, first" format as well as "first middle last, suffix" format
    if "," in name:  
        comma_parts = [part.strip() for part in name.split(",")]
        # check if the second part matches a suffix (after dropping the period)
        if len(comma_parts) > 1 and comma_parts[1].replace(".", "").upper() in suffixes:
            tokens = [t for t in re.split(r"\s+", comma_parts[0]) if t]
            last_name = tokens[-1] if tokens else ""
        else:
            last_name = comma_parts[0]
    else:
        # "first middle last" format
        tokens = [t for t in re.split(r"\s+", name) if t] # (first (middle) last) format
        last_name = tokens[-1] if tokens else ""

    # handle character encoding issues
    # e.g. ALARCÃ“N -> ALARCÓN, DUHÃ‰ -> DUHÉ
    last_name = last_name.replace("Ã“", "O")
    last_name = last_name.replace("Ã‰", "E")

    # remove any non-alphabetic characters, including apostrophes
    # (apostrophes are also causing character encoding issues sometimes - easier to just remove them)
    last_name = re.sub(r"[^A-Za-z]", "", last_name) 

    # manually correct typos 
    last_name = last_name.replace("TYMKOVCH", "TYMKOVICH")
    if last_name == "SCANNLAIN": # can't use .replace() since it also will match to substrings and turn "OSCANNLAIN" into "OOSCANNLAIN"
        last_name = "OSCANNLAIN"

    return last_name

def _extract_last_names_from_list(names):
    return [_extract_last_name(name) for name in names]

def clean_adelglicks_dockets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize docket numbers in AdelGlicks dataframe. 

    (This function only normalizes the dash characters because the docket numbers already appear pretty consistent and clean.)

    Args:
        df: Input dataframe with docket_no1, docket_no2, docket_no3 columns

    Returns:
        DataFrame with standardized docket numbers.
    """
    df = df.copy()

    # Standardize docket number columns
    for col in ['docket_no1', 'docket_no2', 'docket_no3']:
        if col in df.columns:
            # convert docket numbers to strings but prevent nan's from being converted to strings that say "nan"
            df[col] = df[col].fillna('').astype(str) 

            # Normalize dash characters for consistency with CourtListener data
            df[col] = df[col].apply(
                lambda x: _normalize_dash_characters(x) if pd.notna(x) else x)

            # Strip whitespace
            df[col] = df[col].str.strip() if df[col].notna().any() else df[col]

            # Convert any letters to upper case
            df[col] = df[col].str.upper()

    return df


def clean_adelglicks_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize the coding of case outcomes. 
    """
    df = df.copy()
    # strip whitespace and standardize to lowercase
    df['decision'] = df['decision'].str.strip().str.lower()
    df['rev_aff'] = df['rev_aff'].str.strip().str.lower()

    # TODO: we are just ignoring petitions that get denied/dismissed/granted for now because we cannot determine the prevailing party with the AdelGlicks data right now  
    df['district_outcome'] = df['decision'].map({
        'aff_def': 'defendant',
        'aff_pl': 'plaintiff',
        'rev_def': 'plaintiff',
        'rev_pl': 'defendant',
        'mixed': None,
        "denied": None,
        "granted": None,
        "dismissed": None,
    })
    

    df['disposition'] = df['rev_aff'].map({
        'aff': 'affirm',
        'rev': 'reverse',
    })

    # if "decision" was mixed, then set disposition to mixed (the "rev_aff" column doesn't code for this)
    df.loc[df['decision'] == 'mixed', 'disposition'] = 'mixed'
    # if "decision" was denied, this correctly codes that the appellate court affirmed the district court's decision (no change to coding needed)
    # if "decision" was granted, this correctly codes that the appellate court reversed the district court's decision (no change to coding needed)
    # if "decision" was dismissed, this seems more complicated, but we stick with the AdelGLicks coding for now 

    # Create column for final party favored by appellate decision (plaintiff or defendant)
    df['prevailing_party'] = df['decision'].map({
        'aff_def': 'defendant',
        'aff_pl': 'plaintiff',
        'rev_def': 'defendant',
        'rev_pl': 'plaintiff',
        'mixed': 'mixed',
        "denied": None,
        "granted": None,
        "dismissed": None,
    }) 
    # Note the "appellee" column is consistently wrong in AdelGlicks data so if there is a petition we don't know which party won in district court and thus can't code prevailing party for denied,granted, or dismissed petitions. 


    print("Unmapped district outcomes:")
    print(df['district_outcome'].isna().sum())
    print("Unmapped dispositions:")
    print(df['disposition'].isna().sum())
    print("Unmapped prevailing parties:")
    print(df['prevailing_party'].isna().sum())
    print("Total cases in AG data:", df.shape[0])

    return df

def clean_adelglicks_judges(df: pd.DataFrame) -> pd.DataFrame:
    """ Rename the dataframe columns to be consistent with CourtListener judges data.
    """
    df = df.rename(columns={
        "judge_1": "panel_judge_1",
        "judge_2": "panel_judge_2",
        "judge_3": "panel_judge_3",
    })

    # normalize 
    df["panel_judge_1"] = _standardize_judge_string(df["panel_judge_1"])
    df["panel_judge_2"] = _standardize_judge_string(df["panel_judge_2"])
    df["panel_judge_3"] = _standardize_judge_string(df["panel_judge_3"])

    # extract last name 
    df["panel_judge_1"] = df["panel_judge_1"].apply(_extract_last_name)
    df["panel_judge_2"] = df["panel_judge_2"].apply(_extract_last_name)
    df["panel_judge_3"] = df["panel_judge_3"].apply(_extract_last_name)

    return df

def clean_adelglicks_data(adelglicks_raw_path: str, sheet_name: str, 
                          output_path: str) -> pd.DataFrame:
    """
    Clean and standardize AdelGlicks dataset.
    
    Args:
        adelglicks_raw_path: Path to raw AdelGlicks Excel file
        sheet_name: Name of the sheet to read from Excel file
        output_path: Path to save cleaned CSV file
        
    Returns:
        Cleaned DataFrame
    """
    print(f"Loading AdelGlicks data from {adelglicks_raw_path}...")
    df = pd.read_excel(adelglicks_raw_path, sheet_name=sheet_name)
    
    # Standardize docket numbers
    print("Standardizing docket numbers...")
    df = clean_adelglicks_dockets(df)
    
    # Harmonize other variables (year, court/circuit, lead agency)
    # year_filed is already present
    print("Harmonizing other variables...")
    
    df['court_id'] = df['circuit'].map({
        'DC Circuit': 'cadc',
        'First Circuit': 'ca1',
        'Second Circuit': 'ca2',
        'Third Circuit': 'ca3',
        'Fourth Circuit': 'ca4',
        'Fifth Circuit': 'ca5',
        'Sixth Circuit': 'ca6',
        'Seventh Circuit': 'ca7',
        'Eighth Circuit': 'ca8',
        'Ninth Circuit': 'ca9',
        'Tenth Circuit': 'ca10',
        'Eleventh Circuit': 'ca11',
        'Federal Circuit': 'cafc',
    })
    df['lead_agency'] = df['agency']
    # print("Lead agencies found:")
    # print(df['lead_agency'].unique())

    df = clean_adelglicks_outcomes(df)
    df = clean_adelglicks_judges(df)

    # Drop rows that are perfect duplicates 
    df = df.drop_duplicates()
    
    # Save cleaned data
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(output_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    print(f"\nSaved cleaned data to {output_path}")
    
    return df


def clean_adelglicks_main():
    clean_adelglicks_data(
        adelglicks_raw_path=str(ADELGLICKS_RAW_PATH),
        sheet_name=ADELGLICKS_SHEET_NAME,
        output_path=str(ADELGLICKS_CLEANED_PATH)
    )


# ------------------------------------------------------------------------------
# clean court listener clusters
# ------------------------------------------------------------------------------
def find_lead_opinion(cluster_id: int, opinion_df: pd.DataFrame) -> str:
    """
    Find the lead opinion ID for a given cluster.

    Prefer identifying lead opinions in the following order:
    * 020lead
    * 025plurality
    * 015unanimous
    * 010combined (fallback when CourtListener can't identify a specific opinion type or opinion contains multiple types)

    Args:
        cluster_id: Cluster ID to find lead opinion for
        opinion_df: DataFrame with opinion metadata (must have cluster_id and opinion_type columns)

    Returns:
        Lead opinion ID (string), or empty string if not found
    """
    cluster_opinions = opinion_df[opinion_df['cluster_id'] == cluster_id]
    if cluster_opinions.empty:
        return ''

    # Look for lead opinions
    lead_opinion = cluster_opinions[cluster_opinions['opinion_type'] == '020lead']
    if not lead_opinion.empty:
        return lead_opinion.iloc[0]['opinion_id']  # return the first '020lead' opinion id
    plurality_opinion = cluster_opinions[cluster_opinions['opinion_type'] == '025plurality']
    if not plurality_opinion.empty:
        return plurality_opinion.iloc[0]['opinion_id']  # return the first '025plurality' opinion id

    unanimous_opinion = cluster_opinions[cluster_opinions['opinion_type'] == '015unanimous']
    if not unanimous_opinion.empty:
        return unanimous_opinion.iloc[0]['opinion_id']  # return the first '015unanimous' opinion id

    combined_opinion = cluster_opinions[cluster_opinions['opinion_type'] == '010combined']
    if not combined_opinion.empty:
        return combined_opinion.iloc[0]['opinion_id']  # return the first '010combined' opinion id

    # If no lead opinion found
    return ''


def map_clusters_to_lead_opinions(cluster_df: pd.DataFrame,
                                   opinion_df: pd.DataFrame) -> pd.DataFrame:
    """
    Map each cluster to its lead opinion ID.

    Args:
        cluster_df: DataFrame with cluster metadata (must have cluster_id column)
        opinion_df: DataFrame with opinion metadata (must have cluster_id, opinion_id, and opinion_type columns)

    Returns:
        Cluster DataFrame with added lead_opinion_id column
    """
    print("\nMapping clusters to lead opinions...")
    cluster_df = cluster_df.copy()

    if 'cluster_id' not in cluster_df.columns:
        raise ValueError("Cluster dataframe must have 'cluster_id' column.")

    # Check for required columns in opinion_df
    if 'cluster_id' not in opinion_df.columns:
        raise ValueError("Opinion dataframe must have 'cluster_id' column")
    if 'opinion_id' not in opinion_df.columns:
        raise ValueError("Opinion dataframe must have 'opinion_id' column")
    if 'opinion_type' not in opinion_df.columns:
        raise ValueError("Opinion dataframe must have 'opinion_type' column")

    # Map each cluster to its lead opinion
    cluster_df['lead_opinion_id'] = cluster_df['cluster_id'].apply(
        lambda cid: find_lead_opinion(cid, opinion_df)
    )

    # Report statistics
    mapped_count = cluster_df['lead_opinion_id'].notna().sum()
    print(f"  Mapped {mapped_count} clusters ({mapped_count/len(cluster_df)*100:.1f}%) to lead opinions")
    print(f"  {len(cluster_df) - mapped_count} clusters without lead opinions")

    return cluster_df


def parse_courtlistener_docket_string(docket_str: str) -> List[str]:
    """
    Extract individual docket numbers from a CourtListener docket string.

    This function is specifically designed for parsing CourtListener docket numbers.
    Handles various formats including:
    - Multiple dockets separated by commas/semicolons
    - Consolidated cases (e.g., "Consolidated with", "C/w")
    - Docket ranges (e.g., "07-1493 to 07-1499")
    - Various prefixes (Civil Action No., Case No., Docket, etc.)
    - Encoding issues and dash character variants

    Args:
        docket_str: Raw CourtListener docket number string

    Returns:
        List of cleaned individual docket numbers with normalized dash characters
    """
    if pd.isna(docket_str) or not str(docket_str).strip():
        return []

    docket_str = str(docket_str)

    # Normalize dash characters first
    docket_str = _normalize_dash_characters(docket_str)

    # Remove common prefixes and text patterns 
    prefixes = [
        r'Civil Action No\.\s*',
        r'Civil No\.\s*',
        r'Case No\.\s*',
        r'Docket\s+',
        r'Docket No\.\s*',
        r'D.C. No\.\s*',
        r'DOCKETS \s+',
        r'Nos?\.\s*',
        r'Civ\.\s*A\.\s*',
        r'CV-\s*'
    ]
    # text_patterns = [
    #     r'\s*\([^)]*\)\s*', # parenthetical info
    #     r'-[A-Za-z]+$', # suffixes of the form "-XYZ" for some sequence of letters
    #     r'(?:-)cv-',  # non-capturing group ensures we get a match for "-cv-" but only delete one of the dashes to preserve docket number format
    # ]
    for prefix in prefixes:
        docket_str = re.sub(prefix, '', docket_str, flags=re.IGNORECASE)
    # for text_pattern in text_patterns:
    #     docket_str = re.sub(text_pattern, '', docket_str).strip()


    # Handle "Consolidated with" or "C/w" patterns
    consolidated_pattern = r'(?:Consolidated with|C/w)\s+'
    docket_str = re.sub(consolidated_pattern, ', ',
                        docket_str, flags=re.IGNORECASE)

    # Extract all potential docket numbers
    dockets = []

    # Handle ranges like "07-1493 to 07-1499"
    # TODO: handle edge case where there are multiple ranges. e.g. "Nos. 07-1363, 07-1437, 07-1493 to 07-1499, 08-1105 to 08-1107"
    range_match = re.search(r'(\d+)-(\d+)\s+to\s+(\d+)-(\d+)', docket_str)
    if range_match:
        prefix1, start, prefix2, end = range_match.groups()
        # Generate the range
        start_num = int(start)
        end_num = int(end)
        for i in range(start_num, end_num + 1):
            dockets.append(f"{prefix1}-{i:04d}")
        # Remove the range from the string to avoid double-counting
        docket_str = re.sub(r'(\d+)-(\d+)\s+to\s+(\d+)-(\d+)', '', docket_str)

    # Split by common separators: comma, semicolon, ampersand, "and"
    split_pattern = r'\s*[,;&]\s*|\s+and\s+|\s*,\s*and\s*'
    dockets.extend(re.split(split_pattern, docket_str))

    # Convert any letters to upper case
    docket_str = docket_str.upper()

    # not sure if we need/want the below - may be excessive
    # # Extract the core docket number (pattern: digits-digits or just numbers)
    # # Look for patterns like: 22-1101, 17-cv-1179, 1:17-cv-01871, etc.
    # docket_matches = re.findall(
    #     r'\b\d{1,2}:\d{1,2}-[a-z]{2,3}-\d+\b|'  # 1:17-cv-01871
    #     r'\b\d{2,4}-\d{4,5}\b|'  # 22-1101, 07-1363
    #     r'\b\d{2,4}-[a-z]{2,3}-\d+\b',  # 17-cv-1179
    #     item,
    #     flags=re.IGNORECASE
    # )

    # if docket_matches:
    #     dockets.extend(docket_matches)
    # else:
    #     # If no standard pattern found, try to extract any number-number pattern
    #     # This handles cases with parenthetical info
    #     basic_match = re.search(r'(\d{2,4}-\d{4,5})', item)
    #     if basic_match:
    #         dockets.append(basic_match.group(1))

    # Clean up and deduplicate
    cleaned_dockets = []
    seen = set()

    for docket in dockets:
        # Remove punctuation characters
        docket = docket.strip('.,;')

        if docket and docket not in seen:
            cleaned_dockets.append(docket)
            seen.add(docket)

    # sort cleaned dockets alphabetically
    cleaned_dockets.sort()
    return cleaned_dockets


def clean_courtlistener_dockets(
        df: pd.DataFrame,
        docket_col: str = 'docketNumber',
        max_columns: int = 5) -> pd.DataFrame:
    """
    Process a CourtListener dataframe to split docket numbers into separate columns.

    Args:
        df: Input CourtListener dataframe with docket numbers
        docket_col: Name of the column containing docket numbers (default: 'docketNumber')
        max_columns: Maximum number of docket columns to create (default: 5)

    Returns:
        DataFrame with original columns plus docket_no1, docket_no2, ..., docket_no{max_columns},
        and docket_no_others for overflow
    """
    print("\nCleaning docket numbers...")
    df = df.copy()

    # Parse all docket numbers (using CourtListener-specific parser)
    df['docket_numbers_parsed'] = df[docket_col].apply(
        parse_courtlistener_docket_string)

    # Expand out the first X docket numbers in separate columns
    for i in range(max_columns):
        col_name = f'docket_no{i+1}'
        df[col_name] = df['docket_numbers_parsed'].apply(
            lambda x: x[i] if i < len(x) else None
        )

    # Clean up columns
    df['docket_numbers_parsed'] = df['docket_numbers_parsed'].apply(
        lambda x: '; '.join(x) if isinstance(x, list) else x
    )
    df = df.rename(columns={'docketNumber': 'docket_numbers_raw'})

    return df


def drop_nonNEPA_cases(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop CourtListener cases that Maggie marked as not NEPA related.

    Args:
        df: Input cluster metadata dataframe.

    Returns:
        Filtered dataframe with non-NEPA cases removed.
    """
    df = df.copy()
    mb_df = pd.read_csv(USGOV_PL_PATH, encoding = "latin-1") # utf-8 encoding doesn't work for some reason (can't decode byte 0xd5 in position 47954)

    non_nepa_cluster_ids = mb_df.loc[
        mb_df["include_in_analysis"] == 0, "cluster_id"
    ].dropna().astype(str).unique()

    before_count = len(df)
    df = df[~df["cluster_id"].astype(str).isin(non_nepa_cluster_ids)]
    dropped_count = before_count - len(df)
    print(f"Dropped {dropped_count} non-NEPA clusters from metadata")
    print(f"Remaining clusters after non-NEPA filter: {len(df)}")
    return df


def clean_cluster_metadata(cluster_metadata_path: str,
                           opinion_metadata_path: str,
                           output_path: str) -> pd.DataFrame:
    """
    Clean CourtListener cluster metadata and link to lead opinions.

    Args:
        cluster_metadata_path: Path to raw cluster metadata CSV
        opinion_metadata_path: Path to opinion metadata CSV
        output_path: Path to save cleaned cluster metadata CSV

    Returns:
        Cleaned DataFrame with docket numbers split and lead_opinion_id added
    """
    print(f"Loading cluster metadata from {cluster_metadata_path}...")
    cluster_df = pd.read_csv(cluster_metadata_path)

    print(f"\nLoading opinion metadata from {opinion_metadata_path}...")
    opinion_df = pd.read_csv(opinion_metadata_path)

    # handle cases with US gov plaintiffs  
    cluster_df = drop_nonNEPA_cases(cluster_df)

    # Clean docket numbers
    cluster_df = clean_courtlistener_dockets(
        cluster_df, max_columns=5)

    # Harmonize other variables (year, court/circuit, lead agency)
    print("\nHarmonizing other variables...")
    assert 'dateFiled' in cluster_df.columns
    cluster_df['year_filed'] = pd.to_datetime(cluster_df['dateFiled']).dt.year
    # court_id is already in standardized form
    # at the moment we don't have the metadata on federal agencies involved

    # Map to lead opinions
    cluster_df = map_clusters_to_lead_opinions(cluster_df, opinion_df)

    # Re-sort column variables alphabetically
    cluster_df = cluster_df.reindex(sorted(cluster_df.columns), axis=1)
    
    # Drop rows that are duplicates 
    cluster_df = cluster_df.drop_duplicates(subset=["cluster_id"])

    # Clean judge names 
    cluster_df = clean_courtlistener_judges(cluster_df)
    # drop the "judge" column - this is the unclean and often incorrect version 
    cluster_df = cluster_df.drop(columns=["judge"])

    # Save cleaned data
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cluster_df.to_csv(output_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    print(f"\nSaved cleaned cluster metadata to {output_path}")

    return cluster_df


def infer_prevailing_party(df: pd.DataFrame) -> pd.DataFrame:
    """
    Infer prevailing party from district outcome and disposition, then computes univariate scores. 
    """

    assert "opinion_id" in df.columns, "opinion_id column not found in input CSV"
    assert "district_outcome" in df.columns, "district_outcome column not found in input CSV"
    assert "disposition" in df.columns, "disposition column not found in input CSV"

    # Create column for final party favored by appellate decision (plaintiff or defendant)
    df['prevailing_party'] = None 

    # if disposition is affirm, then prevailing party = district outcome
    df.loc[df['disposition'] == 'affirm', 'prevailing_party'] = df['district_outcome']
    # if disposition is reverse, then prevailing party = opposite of district outcome
    df.loc[df['disposition'] == 'reverse', 'prevailing_party'] = df['district_outcome'].map(
        lambda x: 'defendant' if x == 'plaintiff' else 'plaintiff' if x == 'defendant' else None
    )
    # handle mixed and unknown dispositions 
    df.loc[df['disposition'] == 'mixed', 'prevailing_party'] = 'mixed'
    df.loc[df['disposition'] == 'UNK', 'prevailing_party'] = 'UNK'

    # compute univariate scores
    df["district_score"] = df["district_outcome"].map({
        "defendant": 0,
        "mixed": 0.5,
        "plaintiff": 1,
        "UNK": None,
    })
    df["disposition_score"] = df["disposition"].map({
        "affirm": 0,
        "mixed": 0.5,
        "reverse": 1,
        "UNK": None,
    })
    df["prevailing_score"] = df["prevailing_party"].map({
        "defendant": 0,
        "mixed": 0.5,
        "plaintiff": 1,
        "UNK": None,
    })

    # infer the pro- or anti-development stance of the outcome 
    # usually, the US gov is the defendant, and the defendant winning is pro-development 
    df["pro_dev_district_score"] = df["district_outcome"].map({
        "defendant": 1,
        "plaintiff": 0,
        "mixed": 0.5,
        "UNK": None,
    })
    df["pro_dev_prevailing_score"] = df["prevailing_party"].map({
        "defendant": 1,
        "plaintiff": 0,
        "mixed": 0.5,
        "UNK": None,
    })
    # however, sometimes the US gov is the plaintiff. generally in these cases we'll assume that plaintiff/US gov winning is pro development (need to flip the pro-development score). but there are also a couple places where the gov/plaintiff losing, and non-gov defendant winning, is pro-development (ultimately no change to pro-development score). 
    usgov_pl_df = pd.read_csv(USGOV_PL_PATH, encoding = "latin-1") # utf-8 encoding doesn't work for some reason (can't decode byte 0xd5 in position 47954)

    # get everything where the US government is the plaintiff. ignore the stuff Maggie says to drop from analysis. don't touch the stuff where gov losing is pro-development. 
    opinion_ids_to_flip = usgov_pl_df.loc[
            ((usgov_pl_df["include_in_analysis"] == 1) & (usgov_pl_df["gov_losing_as_pro_dev"] != 1)),
            "opinion_id"
        ].unique()
    # flip the mapping for these specific cases 
    flip_mask = df["opinion_id"].isin(opinion_ids_to_flip)
    df.loc[flip_mask, "pro_dev_district_score"] = df.loc[
        flip_mask, "district_outcome"].map({
            "defendant": 0,
            "plaintiff": 1,
            "mixed": 0.5,
            "UNK": None,
        })
    df.loc[flip_mask, "pro_dev_prevailing_score"] = df.loc[
        flip_mask, "prevailing_party"].map({
            "defendant": 0,
            "plaintiff": 1,
            "mixed": 0.5,
            "UNK": None,
        })
    return df


def clean_llm_outcomes():
    """
    Get prevailing party and univariate scores, then save to CSV.
    """
    cl_df = pd.read_csv(LLM_OPINION_CLF_RAW_PATH)
    cl_df = infer_prevailing_party(cl_df)

    # reorder columns
    cl_df = cl_df[["opinion_id", "district_outcome", "disposition", "prevailing_party", "district_score", "disposition_score", "prevailing_score", "pro_dev_district_score", "pro_dev_prevailing_score", "model_id"]]

    # save to CSV
    LLM_OPINION_CLF_PATH.parent.mkdir(parents=True, exist_ok=True)
    cl_df.to_csv(LLM_OPINION_CLF_PATH, index=False)
    print(f"Saved cleaned CourtListener outcomes to {LLM_OPINION_CLF_PATH}")
    return cl_df


def clean_llm_judges() -> pd.DataFrame:
    """
    Clean judge data extracted via LLM: extract last names, extract first three judges from each sequence, and save to CSV.

    Returns:
        Cleaned dataframe with normalized judge columns and added columns for panel_judge_1/2/3 and author_judge_1/2/3.
    """
    df = pd.read_csv(LLM_JUDGES_CLF_RAW_PATH)

    # normalize judge names
    panel_values = _standardize_judge_string(df["panel_judges"])
    author_values = _standardize_judge_string(df["opinion_authors"])

    # identify en banc and per curiam cases
    df["en_banc"] = panel_values.str.contains("EN BANC", regex=False).astype(int)
    df["per_curiam"] = author_values.str.contains("PER CURIAM", regex=False).astype(int)
    panel_values = panel_values.str.replace("EN BANC", "", regex=False)
    author_values = author_values.str.replace("PER CURIAM", "", regex=False)

    # split the semicolon-delimited string into list of judges
    panel_extracted = panel_values.str.split("; ")
    author_extracted = author_values.str.split("; ")
    
    # pull just the last name of each judge
    panel_extracted = panel_extracted.apply(_extract_last_names_from_list)
    author_extracted = author_extracted.apply(_extract_last_names_from_list)


    # pull the first 3 judges from each list (panel and author)
    df["panel_judge_1"] = panel_extracted.str[0].fillna("")
    df["panel_judge_2"] = panel_extracted.str[1].fillna("")
    df["panel_judge_3"] = panel_extracted.str[2].fillna("")

    df["author_judge_1"] = author_extracted.str[0].fillna("")
    df["author_judge_2"] = author_extracted.str[1].fillna("")
    df["author_judge_3"] = author_extracted.str[2].fillna("")

    # save to CSV
    LLM_JUDGES_CLF_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(LLM_JUDGES_CLF_PATH, index=False)
    print(f"Saved cleaned CourtListener judges to {LLM_JUDGES_CLF_PATH}")
    return df


def clean_courtlistener_judges(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean judge data that already existed in CourtListener.

    Parse the single concatenated judge string into separate columns and keep
    CourtListener-derived judge columns distinct from LLM-derived columns.

    Args:
        df: Cluster metadata dataframe containing CourtListener judge text in the "judge" column.

    Returns:
        Dataframe with added columns:
        `cl_judges`, `cl_judge_1`, `cl_judge_2`, `cl_judge_3`, 
        and `cl_per_curiam`.
    """
    assert "judge" in df.columns, "'judge' column not found in input CSV"
    df = df.copy()

    # standardize (all caps, strip whitespace)
    judge_values = _standardize_judge_string(df["judge"])

    # normalize "and" variants (Oxford comma and bare "and")
    judge_values = judge_values.str.replace(", AND ", ", ").str.replace(" AND ", ", ")

    # drop data error 
    judge_values = judge_values.str.replace("VIRGINIA STRASSER (ARGUED)", "")

    # handle per curiam cases
    # (no "en banc" keywords identified in the judge strings)
    df["cl_per_curiam"] = judge_values.str.contains("PER CURIAM", regex=False).astype(int)
    judge_values = judge_values.str.replace("PER CURIAM", "", regex=False)

    df["cl_judges"] = judge_values

    token_errors = {
        "CIRCUIT JUDGE", "CIRCUIT JUDGES",
        "CHIEF JUDGE", "CHIEF JUDGES",
        "DISTRICT JUDGE", "DISTRICT JUDGES",
        "SENIOR CIRCUIT JUDGE",
        "SENIOR DISTRICT JUDGE",
        "SENIOR JUDGE", 
        "'SENIOR",
        "CONCURRENC",
        "CONCURRENCE",
        "CONCURRENCES",
        "SUPREME",
        "DISSENT"
    }
    suffix_tokens = {"II", "III", "IV", "V", "JR", "SR"}

    def _parse_judge_string(s):
        if not s:
            return []
        tokens = [t.strip() for t in s.split(", ") if t.strip()]
        last_names = []
        for token in tokens:
            if token in token_errors: # drop erroneous tokens 
                continue
            if token.replace(".", "") in suffix_tokens: # drop suffix tokens
                continue
            last_name = _extract_last_name(token)
            if last_name:
                last_names.append(last_name)
        return last_names

    judges_extracted = judge_values.apply(_parse_judge_string)
    df["cl_judge_1"] = judges_extracted.str[0].fillna("")
    df["cl_judge_2"] = judges_extracted.str[1].fillna("")
    df["cl_judge_3"] = judges_extracted.str[2].fillna("")

    return df


def merge_cluster_metadata_w_llm_features(
    cluster_metadata_path: str,
    llm_outcomes_path: str,
    llm_judges_path: str,
    output_path: str
) -> pd.DataFrame:
    """
    Merge LLM-coded features (case outcomes and judges) with cluster metadata.
    
    Args:
        cluster_metadata_path: Path to cleaned cluster metadata CSV
        llm_outcomes_path: Path to cleaned LLM opinion coding CSV
        llm_judges_path: Path to cleaned LLM judges coding CSV
        output_path: Path to save merged CSV
        
    Returns:
        Merged DataFrame with cluster metadata and LLM-extracted features (case outcomes and judge names)
    """
    print("\nMerging LLM-coded features with cluster metadata...")
    cluster_df = pd.read_csv(cluster_metadata_path, dtype={"cluster_id": str, "lead_opinion_id": str})
    llm_outcomes_df = pd.read_csv(llm_outcomes_path, dtype={"opinion_id": str})
    llm_outcomes_df = llm_outcomes_df.rename(columns={"model_id": "outcomes_model_id"})
    judges_df = pd.read_csv(llm_judges_path, dtype={"opinion_id": str})
    judges_df = judges_df.rename(columns={"model_id": "judges_model_id"})
    
    # Merge cluster metadata to LLM-extracted features using lead_opinion_id from cluster metadata
    merged_df = cluster_df.merge(
        llm_outcomes_df,
        left_on="lead_opinion_id",
        right_on="opinion_id",
        how="left",
    )
    merged_df = merged_df.drop(columns=["opinion_id"]) # duplicate of lead_opinion_id
    merged_df = merged_df.merge(
        judges_df,
        left_on="lead_opinion_id",
        right_on="opinion_id",
        how="left",
    )
    merged_df = merged_df.drop(columns=["opinion_id"]) # duplicate of lead_opinion_id
    
    # Save merged data
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(output_path_obj, index=False, quoting=csv.QUOTE_NONNUMERIC)
    print(f"Saved merged data to {output_path_obj}")
    
    # Print summary statistics
    total_clusters = len(merged_df)

    clusters_with_outcomes = merged_df["prevailing_score"].notna().sum()
    print(f"Total clusters: {total_clusters}")
    print(f"Clusters with LLM outcomes: {clusters_with_outcomes} ({clusters_with_outcomes/total_clusters*100:.1f}%)")

    clusters_with_judges = merged_df["panel_judges"].notna().sum()
    print(f"Clusters with LLM judges: {clusters_with_judges} ({clusters_with_judges/total_clusters*100:.1f}%)")

    return merged_df


def clean_courtlistener_clusters_main():
    # Find the most recent run directory
    # TODO: maybe move this to separate function or pass as parameter
    run_dirs = sorted([d for d in COURTLISTENER_RAW_DIR.iterdir() if d.is_dir() and d.name.startswith('run_')])
    if not run_dirs:
        raise FileNotFoundError(f"No run directories found in {COURTLISTENER_RAW_DIR}")

    latest_run_dir = run_dirs[-1]
    print(f"Using run directory: {latest_run_dir.name}")

    cluster_metadata_path = latest_run_dir / "cluster_metadata.csv"
    opinion_metadata_path = latest_run_dir / "opinion_metadata.csv"

    # Clean the data
    clean_cluster_metadata(
        cluster_metadata_path=str(cluster_metadata_path),
        opinion_metadata_path=str(opinion_metadata_path),
        output_path=str(COURTLISTENER_CLUSTER_CLEANED_PATH)
    )

    clean_llm_outcomes() # save a copy of the LLM-coded outcomes and adds a column for prevailing party 
    clean_llm_judges() # save a cleaned copy of LLM-coded judges data

    # Merge LLM-coded outcomes and judges with cluster metadata
    merge_cluster_metadata_w_llm_features(
        cluster_metadata_path=str(COURTLISTENER_CLUSTER_CLEANED_PATH),
        llm_outcomes_path=str(LLM_OPINION_CLF_PATH),
        llm_judges_path=str(LLM_JUDGES_CLF_PATH),
        output_path=str(COURTLISTENER_METADATA_W_FTRS_PATH)
    )

    print("Done!")


# ------------------------------------------------------------------------------
# merge cases by docket numbers
# ------------------------------------------------------------------------------
def get_docket_set(row, docket_cols=None):
    """
    Extract a set of non-empty docket numbers from a row.

    Args:
        row: DataFrame row
        docket_cols: List of docket column names to check

    Returns:
        Set of non-empty docket numbers (normalized: uppercase, stripped)
    """
    dockets = set()

    # CourtListener format
    if 'docket_numbers_parsed' in row.index:
        parsed = row['docket_numbers_parsed']
        if pd.notna(parsed):
            for docket in str(parsed).split('; '):
                docket = docket.strip().upper()
                if docket and docket != 'NAN':
                    dockets.add(docket)
        return dockets

    # AdelGlicks format: docket_no1, docket_no2, docket_no3
    for col in docket_cols:
        if col in row.index:
            docket = row[col]
            if pd.notna(docket) and str(docket).strip() and str(docket).strip().upper() != 'NAN':
                dockets.add(str(docket).strip().upper())
    return dockets


def compute_all_matches(cl_df, ag_df):
    """
    Compute all matches between CourtListener and AdelGlicks cases.

    Rules:
    * Restrict matches to cases within the same court.
    * Match using the set of docket numbers.

    Args:
        cl_df: CourtListener dataframe with docket_numbers_parsed column
        ag_df: AdelGlicks dataframe with docket_no1, docket_no2, docket_no3

    Returns:
        Tuple of (matches list, cl_docket_sets dict, ag_docket_sets dict)
    """
    # Verify court_id column exists
    if 'court_id' not in cl_df.columns:
        raise ValueError("court_id column not found in CourtListener dataframe")
    if 'court_id' not in ag_df.columns:
        raise ValueError("court_id column not found in AdelGlicks dataframe")

    # Extract docket sets for each row
    print("Extracting docket number sets...")
    cl_docket_sets = cl_df.apply(lambda row: get_docket_set(row), axis=1)  # pd.Series

    ag_docket_cols = ['docket_no1', 'docket_no2', 'docket_no3']
    ag_docket_sets = ag_df.apply(lambda row: get_docket_set(row, ag_docket_cols), axis=1)

    matches = []

    print("Grouping cases by court...")
    cl_courts = cl_df['court_id']
    ag_courts = ag_df['court_id']
    cl_court_to_indices = cl_courts.groupby(cl_courts).groups
    ag_court_to_indices = ag_courts.groupby(ag_courts).groups

    for court_id, cl_indices in cl_court_to_indices.items():
        ag_indices = ag_court_to_indices.get(court_id)

        if ag_indices is None:
            continue

        for cl_idx in cl_indices:
            cl_dockets = cl_docket_sets.get(cl_idx, set())
            if not cl_dockets:
                continue

            for ag_idx in ag_indices:
                ag_dockets = ag_docket_sets.get(ag_idx, set())
                if not ag_dockets:
                    continue

                overlap = cl_dockets.intersection(ag_dockets)
                if overlap:
                    matches.append({
                        'cluster_id': cl_df.loc[cl_idx, 'cluster_id'],
                        'adelglicks_id': ag_df.loc[ag_idx, 'id_num'],
                        'court_id': cl_df.loc[cl_idx, 'court_id'],
                        'CL_year_filed': cl_df.loc[cl_idx, 'year_filed'],
                        'AG_year_filed': ag_df.loc[ag_idx, 'year_filed'],
                        'CL_AG_year_match': (
                            cl_df.loc[cl_idx, 'year_filed']
                            == ag_df.loc[ag_idx, 'year_filed']
                        ),
                        'year_filed_diff': (
                            cl_df.loc[cl_idx, 'year_filed']
                            - ag_df.loc[ag_idx, 'year_filed']
                        ),
                        'CL_docket_count': len(cl_dockets),
                        'AG_docket_count': len(ag_dockets),
                        'overlap_count': len(overlap),
                        'CL_dockets': "; ".join(sorted(cl_dockets)),
                        'AG_dockets': "; ".join(sorted(ag_dockets)),
                        'overlapping_dockets': "; ".join(sorted(overlap)),
                        'AG_has_outcome': (
                            pd.notna(ag_df.loc[ag_idx, 'district_outcome'])
                            and pd.notna(ag_df.loc[ag_idx, 'disposition'])
                        ),
                        'is_perfect_match': cl_dockets == ag_dockets,
                        'CL_subset_of_AG': cl_dockets.issubset(ag_dockets),
                        'AG_subset_of_CL': ag_dockets.issubset(cl_dockets),
                    })

    matches_df = pd.DataFrame(matches) if matches else pd.DataFrame()

    # remove duplicates
    matches_df = matches_df.drop_duplicates()

    return matches_df, cl_docket_sets, ag_docket_sets


def find_cases_with_multiple_matches(matches_df):
    """
    Add indicator columns for CL/AG cases matched to multiple other cases.

    Returns:
        matches_df with two new boolean columns:
        - cl_has_multiple_matches
        - ag_has_multiple_matches
    """
    if matches_df is None or len(matches_df) == 0:
        return matches_df

    cl_counts = matches_df.groupby('cluster_id').size()
    ag_counts = matches_df.groupby('adelglicks_id').size()
    matches_df['CL_has_multiple_matches'] = matches_df['cluster_id'].map(
        cl_counts.gt(1)
    ).fillna(False)
    matches_df['AG_has_multiple_matches'] = matches_df['adelglicks_id'].map(
        ag_counts.gt(1)
    ).fillna(False)

    return matches_df


def compute_match_statistics(cl_df, ag_df, matches_df, cl_docket_sets, ag_docket_sets):
    """
    Compute statistics on docket number matches.

    Args:
        cl_df: CourtListener dataframe
        ag_df: AdelGlicks dataframe
        matches_df: DataFrame of matches
        cl_docket_sets: Dictionary mapping CL indices to docket sets
        ag_docket_sets: Dictionary mapping AG indices to docket sets

    Returns:
        Dictionary with match statistics
    """
    stats = {}

    if len(matches_df) > 0:
        stats['total_matches'] = len(matches_df)
        stats['unique_cl_matched'] = matches_df['cluster_id'].nunique()
        stats['unique_ag_matched'] = matches_df['adelglicks_id'].nunique()
        stats['perfect_matches'] = matches_df['is_perfect_match'].sum()
        stats['cl_subset_of_ag'] = matches_df['CL_subset_of_AG'].sum()
        stats['ag_subset_of_cl'] = matches_df['AG_subset_of_CL'].sum()
        stats['cl_strict_subset_of_ag'] = stats['cl_subset_of_ag'] - stats['perfect_matches']
        stats['ag_strict_subset_of_cl'] = stats['ag_subset_of_cl'] - stats['perfect_matches']

        # Multiple match statistics
        cl_match_counts = matches_df.groupby('cluster_id').size()
        ag_match_counts = matches_df.groupby('adelglicks_id').size()
        stats['cl_cases_with_multiple_matches'] = (cl_match_counts > 1).sum()
        stats['ag_cases_with_multiple_matches'] = (ag_match_counts > 1).sum()

        # Perfect matches that also have multiple matches
        cl_perfect_any = matches_df[matches_df['is_perfect_match']].groupby('cluster_id').size()
        ag_perfect_any = matches_df[matches_df['is_perfect_match']].groupby('adelglicks_id').size()
        stats['cl_cases_perfect_and_multiple'] = (
            cl_perfect_any.reindex(cl_match_counts.index, fill_value=0).gt(0)
            & cl_match_counts.gt(1)
        ).sum()
        stats['ag_cases_perfect_and_multiple'] = (
            ag_perfect_any.reindex(ag_match_counts.index, fill_value=0).gt(0)
            & ag_match_counts.gt(1)
        ).sum()

        # Overlap count distribution
        stats['overlap_distribution'] = matches_df['overlap_count'].value_counts().to_dict()

        # Match quality breakdown
        stats['match_quality'] = {
            'perfect': stats['perfect_matches'],
            'cl_subset': stats['cl_subset_of_ag'],
            'ag_subset': stats['ag_subset_of_cl'],
            'cl_strict_subset': stats['cl_strict_subset_of_ag'],
            'ag_strict_subset': stats['ag_strict_subset_of_cl'],
            'partial': len(matches_df) - stats['perfect_matches']
        }
    else:
        stats['total_matches'] = 0
        stats['unique_cl_matched'] = 0
        stats['unique_ag_matched'] = 0
        stats['perfect_matches'] = 0
        stats['cl_subset_of_ag'] = 0
        stats['ag_subset_of_cl'] = 0
        stats['cl_cases_with_multiple_matches'] = 0
        stats['ag_cases_with_multiple_matches'] = 0
        stats['cl_cases_perfect_and_multiple'] = 0
        stats['ag_cases_perfect_and_multiple'] = 0
        stats['overlap_distribution'] = {}
        stats['match_quality'] = {}

    # Overall dataset statistics
    stats['total_cl_cases'] = len(cl_df)
    stats['total_ag_cases'] = len(ag_df)
    stats['cl_cases_with_dockets'] = (cl_docket_sets.apply(len) > 0).sum()
    stats['ag_cases_with_dockets'] = (ag_docket_sets.apply(len) > 0).sum()
    stats['cl_cases_unmatched'] = stats['total_cl_cases'] - stats['unique_cl_matched']
    stats['ag_cases_unmatched'] = stats['total_ag_cases'] - stats['unique_ag_matched']

    return stats


def _format_merge_statistics(stats):
    """Format match statistics in a readable format."""
    lines = []
    lines.append("\n" + "="*60)
    lines.append("DOCKET NUMBER MATCH STATISTICS")
    lines.append("="*60)

    lines.append("\nDataset Overview:")
    lines.append(f"  CourtListener cases: {stats['total_cl_cases']}")
    lines.append(f"  AdelGlicks cases: {stats['total_ag_cases']}")

    lines.append("\nMatch Overview:")
    lines.append(f"  Total matches found: {stats['total_matches']}")
    lines.append(f"  Unique CourtListener cases matched: {stats['unique_cl_matched']}")
    lines.append(f"  Unique AdelGlicks cases matched: {stats['unique_ag_matched']}")
    lines.append(f"  CourtListener cases unmatched: {stats['cl_cases_unmatched']}")
    lines.append(f"  AdelGlicks cases unmatched: {stats['ag_cases_unmatched']}")

    if stats['total_matches'] > 0:
        lines.append("\nMultiple Match Statistics:")
        lines.append(f"  CL cases with multiple matches: {stats['cl_cases_with_multiple_matches']}")
        lines.append(f"  AG cases with multiple matches: {stats['ag_cases_with_multiple_matches']}")
        lines.append(f"  CL cases perfect + multiple: {stats['cl_cases_perfect_and_multiple']}")
        lines.append(f"  AG cases perfect + multiple: {stats['ag_cases_perfect_and_multiple']}")

        lines.append("\nMatch Quality:")
        lines.append(f"  Perfect matches (identical docket sets): {stats['match_quality'].get('perfect', 0)}")
        lines.append(f"  CL strict subset of AG (all CL dockets in AG): {stats['match_quality'].get('cl_strict_subset', 0)}")
        lines.append(f"  AG strict subset of CL (all AG dockets in CL): {stats['match_quality'].get('ag_strict_subset', 0)}")
        lines.append(f"  Partial matches (some overlap): {stats['match_quality'].get('partial', 0)}")

        lines.append("\nOverlap Count Distribution:")
        for overlap_count, match_count in sorted(stats['overlap_distribution'].items()):
            lines.append(f"  {overlap_count} docket(s) overlap: {match_count} matches")

    return "\n".join(lines)


def _print_merge_statistics(stats):
    """Print match statistics in a readable format."""
    output = _format_merge_statistics(stats)
    print(output)
    return output


def merge_cases_by_docket_main():
    # Load cleaned datasets
    cl_df = pd.read_csv(COURTLISTENER_CLUSTER_CLEANED_PATH)
    ag_df = pd.read_csv(ADELGLICKS_CLEANED_PATH)

    # Compute all matches
    matches_df, cl_docket_sets, ag_docket_sets = compute_all_matches(cl_df, ag_df)
    matches_df = find_cases_with_multiple_matches(matches_df)

    # Compute statistics
    stats = compute_match_statistics(cl_df, ag_df, matches_df, cl_docket_sets, ag_docket_sets)

    # Print statistics and save to text file
    stats_output = _print_merge_statistics(stats)
    COURTLISTENER_AG_MATCH_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COURTLISTENER_AG_MATCH_STATS_PATH.write_text(stats_output, encoding="utf-8")

    # Save match data to CSV
    output_path = COURTLISTENER_AG_MATCHING_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    matches_df.to_csv(output_path, index=False)
    print(f"\nSaved matching data to: {output_path}")


# ------------------------------------------------------------------------------
# train/test/val split assignments 
# ------------------------------------------------------------------------------

def assign_val_test_split(
    matches_df: pd.DataFrame,
    seed: int = 42,
    split_col: str = "dataset_split",
) -> pd.DataFrame:
    """
    Assign 50/50 validation/test split for AdelGLicks cases that were perfectly matched to CourtListener cases and have case outcomes coded. Assignments are random and stratified by court.

    Args:
        matches_df: DataFrame from CourtListener_AdelGlicks_matching.csv
        seed: Random seed for reproducibility
        split_col: Column name for dataset split assignment

    Returns:
        DataFrame with split assignments in split_col.
    """
    # Note: the sklearn function can do this slightly more elegantly, *except* 
    # in the case where a group has only a single case, in which case it 
    # crashes. hence we are just doing this manually here. 
    required_cols = {"is_perfect_match", "AG_has_outcome", "court_id"}
    missing = required_cols - set(matches_df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = matches_df.copy()
    df[split_col] = ""

    eligible_mask = df["is_perfect_match"].astype(
        bool) & df["AG_has_outcome"].astype(bool)
    eligible_df = df[eligible_mask]

    rng = np.random.default_rng(seed)
    val_indices = []
    test_indices = []
    leftovers = []

    for _, group in eligible_df.groupby(["court_id"]):
        group_indices = group.index.to_numpy()
        rng.shuffle(group_indices)
        split_point = len(group_indices) // 2
        val_indices.extend(group_indices[:split_point])
        test_indices.extend(group_indices[split_point:split_point * 2])
        if len(group_indices) % 2 == 1:
            leftovers.append(group_indices[-1])

    # Randomize leftover order, then distribute to keep overall counts balanced
    leftovers = np.array(leftovers)
    rng.shuffle(leftovers)
    for idx in leftovers:
        if len(val_indices) <= len(test_indices):
            val_indices.append(idx)
        else:
            test_indices.append(idx)

    df.loc[val_indices, split_col] = "val"
    df.loc[test_indices, split_col] = "test"

    print(f"Eligible rows for split: {len(eligible_df)}")
    print(f"Validation rows: {len(val_indices)}")
    print(f"Test rows: {len(test_indices)}")

    return df


def save_val_and_test_subsets(matches_df):
    """
    Save the val and test sets in their own files as a permanent record to avoid accidental modification.
    """
    val_df = matches_df[matches_df["dataset_split"] == "val"].copy()
    test_df = matches_df[matches_df["dataset_split"] == "test"].copy()

    FTR_ASSIGNMENTS_DIR.mkdir(parents=True, exist_ok=True)
    val_df.to_csv(AG_VAL_ASSIGNMENTS_PATH, index=False)
    test_df.to_csv(AG_TEST_ASSIGNMENTS_PATH, index=False)

    print(f"Saved val subset to: {AG_VAL_ASSIGNMENTS_PATH}")
    print(f"Saved test subset to: {AG_TEST_ASSIGNMENTS_PATH}")


def save_cl_train_split(matches_df):
    """
    Save all CourtListener cases excluding val/test cases as the train set.
    """
    cl_df = pd.read_csv(COURTLISTENER_CLUSTER_CLEANED_PATH)
    exclude_ids = matches_df.loc[matches_df["is_perfect_match"],
                                 "cluster_id"].unique()
    # print(exclude_ids)

    train_matches = matches_df[~matches_df["cluster_id"].isin(exclude_ids)]
    train_matches.loc[:, "dataset_split"] = "train"

    unmatched_cl = cl_df[~cl_df["cluster_id"].isin(
        matches_df["cluster_id"])].copy()
    unmatched_cl = unmatched_cl[~unmatched_cl["cluster_id"].isin(exclude_ids)]

    # Build rows with same columns as matches_df
    base_cols = list(matches_df.columns)
    cl_train_unmatched = pd.DataFrame(columns=base_cols)
    cl_train_unmatched["cluster_id"] = unmatched_cl["cluster_id"]
    cl_train_unmatched["court_id"] = unmatched_cl["court_id"]
    cl_train_unmatched["CL_year_filed"] = unmatched_cl["year_filed"]
    cl_train_unmatched["dataset_split"] = "train"

    cl_train_df = pd.concat(
        [train_matches, cl_train_unmatched], ignore_index=True)

    # Save output
    CL_TRAIN_ASSIGNMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    cl_train_df.to_csv(CL_TRAIN_ASSIGNMENTS_PATH, index=False)
    print(f"Saved CL train set to: {CL_TRAIN_ASSIGNMENTS_PATH}")


def assign_val_test_split_main():
    matches_df = pd.read_csv(COURTLISTENER_AG_MATCHING_PATH)
    matches_df = assign_val_test_split(matches_df)

    # Save outputs
    COURTLISTENER_AG_MATCHING_SPLIT_PATH.parent.mkdir(
        parents=True, exist_ok=True)
    matches_df.to_csv(COURTLISTENER_AG_MATCHING_SPLIT_PATH, index=False)
    print(f"\nSaved split data to: {COURTLISTENER_AG_MATCHING_SPLIT_PATH}")

    save_val_and_test_subsets(matches_df)
    save_cl_train_split(matches_df)


def merge_cl_train_w_llm_features(
    train_assignments_path: Path = CL_TRAIN_ASSIGNMENTS_PATH,
    output_path: Path = CL_TRAIN_PREDICTIONS_PATH,
) -> pd.DataFrame:
    """ Merge CL train data with LLM-coded features (case outcomes and judges).
    
    Args:
        train_assignments_path: Path to CL train assignments CSV. 
        output_path: Path to save merged results.
    
    Returns:
        DataFrame with merged train data and predictions
    """
    # Load data
    train_assignments = pd.read_csv(train_assignments_path, dtype={"cluster_id": str}) 
    cl_df = pd.read_csv(COURTLISTENER_CLUSTER_CLEANED_PATH, dtype={"cluster_id": str, "lead_opinion_id": str})
    pred_outcomes_df = pd.read_csv(LLM_OPINION_CLF_PATH, dtype={"opinion_id": str})
    pred_outcomes_df = pred_outcomes_df.rename(columns={"model_id": "outcomes_model_id"})
    pred_outcomes_df = infer_prevailing_party(pred_outcomes_df)

    judges_df = pd.read_csv(LLM_JUDGES_CLF_PATH, dtype={"opinion_id": str})
    judges_df = judges_df.rename(columns={"model_id": "judges_model_id"})
    
    # Validate required columns
    assert "lead_opinion_id" in cl_df.columns, "lead_opinion_id missing from CourtListener cluster metadata"
    assert "opinion_id" in pred_outcomes_df.columns, "opinion_id missing from LLM coded outcomes"
    assert "cluster_id" in train_assignments.columns, "cluster_id missing from train assignments"

    # Merge with CL to get lead opinion id
    merged = train_assignments.merge(
        cl_df[["cluster_id", "lead_opinion_id"]],
        on="cluster_id",
        how="left",
    )
    
    # Merge with LLM-extracted features (case outcomes and judges)
    merged = merged.merge(
        pred_outcomes_df,
        left_on="lead_opinion_id",
        right_on="opinion_id",
        how="left",
    )
    merged = merged.drop(columns=["opinion_id"]) # duplicate of lead_opinion_id
    merged = merged.merge(
        judges_df,
        left_on="lead_opinion_id",
        right_on="opinion_id",
        how="left",
    )
    merged = merged.drop(columns=["opinion_id"]) # duplicate of lead_opinion_id
    
    merged = merged.rename(columns={
        "district_outcome": "district_outcome_pred",
        "disposition": "disposition_pred"
    })

    # Save output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    print(f"Saved merged CL train predictions to: {output_path}")
    
    # Print summary statistics
    total_cases = len(merged)

    cases_with_predictions = merged["district_outcome_pred"].notna().sum()
    print(f"Total train cases: {total_cases}")
    print(f"Cases with predictions: {cases_with_predictions} ({cases_with_predictions/total_cases*100:.1f}%)")

    cases_with_judges = merged["panel_judges"].notna().sum()
    print(f"Cases with judges: {cases_with_judges} ({cases_with_judges/total_cases*100:.1f}%)")
    
    return merged


def flip_district_outcome(
    input_path: Path = LLM_OPINION_CLF_RAW_PATH,
) -> pd.DataFrame:
    """
    Flip district_outcome values in LLM opinion coding CSV.
    
    Flips "defendant" to "plaintiff" and "plaintiff" to "defendant".
    Leaves "mixed" and "UNK" unchanged.
    
    Args:
        input_path: Path to input CSV file with district_outcome column
        
    Output:
        Saves flipped district_outcome values to a new CSV file with "_district_flipped" suffix
    """
    # print(f"Loading LLM opinion coding from {input_path}...")
    df = pd.read_csv(input_path)
    assert "district_outcome" in df.columns, "district_outcome column not found in input CSV"
    
    # Flip district_outcome values
    print("Flipping district_outcome values...")
    df["district_outcome"] = df["district_outcome"].map({
        "defendant": "plaintiff",
        "plaintiff": "defendant",
    }).fillna(df["district_outcome"])  # Keep original value if not in mapping (e.g., "mixed", "UNK", NaN)
    
    # Save output
    input_path_obj = Path(input_path)
    output_path = input_path_obj.parent / f"{input_path_obj.stem}_district_flipped{input_path_obj.suffix}"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved flipped district_outcome data to: {output_path}")
    
    return df



# ------------------------------------------------------------------------------

def main():
    clean_adelglicks_main()
    clean_courtlistener_clusters_main()
    merge_cases_by_docket_main()
    assign_val_test_split_main()
    # flip_district_outcome() # temporary workaround because it seems like the LLM coded everything the opposite way 
    merge_cl_train_w_llm_features() # saves a copy of courtlistener data excluded from the val/test sets and merges with predictions 


if __name__ == "__main__":
    main()

