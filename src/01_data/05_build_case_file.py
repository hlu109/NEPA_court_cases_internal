"""
Clean CourtListener cluster metadata and merge it with Gemini-coded case outcomes and judges.
"""

import csv
import re
from typing import List
import pandas as pd
import sys
from pathlib import Path

# Add project root to Python path to allow imports from src.utils
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config import (COURTLISTENER_CLUSTER_CLEANED_PATH,
                          LLM_OPINION_RAW_PATH, LLM_OPINION_PATH,
                          LLM_JUDGES_PATH, COURTLISTENER_METADATA_W_FTRS_PATH,
                          USGOV_PL_PATH, JUDGESHIPS_CLEAN_PATH)
from utils.case_cleaning_utils import (normalize_dash_characters,
                                       infer_prevailing_party,
                                       get_latest_courtlistener_run)
from utils.judge_names import parse_judge_name, standardize_judges_raw


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
    lead_opinion = cluster_opinions[cluster_opinions['opinion_type'] ==
                                    '020lead']
    if not lead_opinion.empty:
        return lead_opinion.iloc[0][
            'opinion_id']  # return the first '020lead' opinion id
    plurality_opinion = cluster_opinions[cluster_opinions['opinion_type'] ==
                                         '025plurality']
    if not plurality_opinion.empty:
        return plurality_opinion.iloc[0][
            'opinion_id']  # return the first '025plurality' opinion id

    unanimous_opinion = cluster_opinions[cluster_opinions['opinion_type'] ==
                                         '015unanimous']
    if not unanimous_opinion.empty:
        return unanimous_opinion.iloc[0][
            'opinion_id']  # return the first '015unanimous' opinion id

    combined_opinion = cluster_opinions[cluster_opinions['opinion_type'] ==
                                        '010combined']
    if not combined_opinion.empty:
        return combined_opinion.iloc[0][
            'opinion_id']  # return the first '010combined' opinion id

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
        lambda cid: find_lead_opinion(cid, opinion_df))

    # Report statistics
    mapped_count = cluster_df['lead_opinion_id'].notna().sum()
    print(
        f"  Mapped {mapped_count} clusters ({mapped_count/len(cluster_df)*100:.1f}%) to lead opinions"
    )
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
    docket_str = normalize_dash_characters(docket_str)

    # Remove common prefixes and text patterns
    prefixes = [
        r'Civil Action No\.\s*', r'Civil No\.\s*', r'Case No\.\s*',
        r'Docket\s+', r'Docket No\.\s*', r'D.C. No\.\s*', r'DOCKETS \s+',
        r'Nos?\.\s*', r'Civ\.\s*A\.\s*', r'CV-\s*'
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
    docket_str = re.sub(consolidated_pattern,
                        ', ',
                        docket_str,
                        flags=re.IGNORECASE)

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


def clean_courtlistener_dockets(df: pd.DataFrame,
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
            lambda x: x[i] if i < len(x) else None)

    # Clean up columns
    df['docket_numbers_parsed'] = df['docket_numbers_parsed'].apply(
        lambda x: '; '.join(x) if isinstance(x, list) else x)
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
    mb_df = pd.read_csv(
        USGOV_PL_PATH, encoding="latin-1"
    )  # utf-8 encoding doesn't work for some reason (can't decode byte 0xd5 in position 47954)

    non_nepa_cluster_ids = mb_df.loc[mb_df["include_in_analysis"] == 0,
                                     "cluster_id"].dropna().astype(
                                         str).unique()

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
    cluster_df = clean_courtlistener_dockets(cluster_df, max_columns=5)

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


def clean_llm_outcomes():
    """
    Get prevailing party and univariate scores, then save to CSV.
    """
    cl_df = pd.read_csv(LLM_OPINION_RAW_PATH)
    cl_df = infer_prevailing_party(cl_df)

    # reorder columns
    cl_df = cl_df[[
        "opinion_id", "district_outcome", "disposition", "prevailing_party",
        "district_score", "disposition_score", "prevailing_score",
        "pro_dev_district_score", "pro_dev_prevailing_score", "model_id"
    ]]

    # save to CSV
    LLM_OPINION_PATH.parent.mkdir(parents=True, exist_ok=True)
    cl_df.to_csv(LLM_OPINION_PATH, index=False)
    print(f"Saved cleaned CourtListener outcomes to {LLM_OPINION_PATH}")
    return cl_df


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
    judge_values = standardize_judges_raw(df["judge"])

    # normalize "and" variants (Oxford comma and bare "and")
    judge_values = judge_values.str.replace(", AND ",
                                            ", ").str.replace(" AND ", ", ")

    # drop data error
    judge_values = judge_values.str.replace("VIRGINIA STRASSER (ARGUED)", "")

    # handle per curiam cases
    # (no "en banc" keywords identified in the judge strings)
    df["cl_per_curiam"] = judge_values.str.contains("PER CURIAM",
                                                    regex=False).astype(int)
    judge_values = judge_values.str.replace("PER CURIAM", "", regex=False)

    df["cl_judges"] = judge_values

    token_errors = {
        "CIRCUIT JUDGE", "CIRCUIT JUDGES", "CHIEF JUDGE", "CHIEF JUDGES",
        "DISTRICT JUDGE", "DISTRICT JUDGES", "SENIOR CIRCUIT JUDGE",
        "SENIOR DISTRICT JUDGE", "SENIOR JUDGE", "'SENIOR", "CONCURRENC",
        "CONCURRENCE", "CONCURRENCES", "SUPREME", "DISSENT"
    }
    suffix_tokens = {"II", "III", "IV", "V", "JR", "SR"}

    def _parse_judge_string(s):
        if not s:
            return []
        tokens = [t.strip() for t in s.split(", ") if t.strip()]
        last_names = []
        for token in tokens:
            if token in token_errors:  # drop erroneous tokens
                continue
            if token.replace(".", "") in suffix_tokens:  # drop suffix tokens
                continue
            last_name = parse_judge_name(token)["last"]
            if last_name:
                last_names.append(last_name)
        return last_names

    judges_extracted = judge_values.apply(_parse_judge_string)
    df["cl_judge_1"] = judges_extracted.str[0].fillna("")
    df["cl_judge_2"] = judges_extracted.str[1].fillna("")
    df["cl_judge_3"] = judges_extracted.str[2].fillna("")

    return df


def merge_cluster_metadata_w_llm_features(cluster_metadata_path: str,
                                          llm_outcomes_path: str,
                                          llm_judges_path: str,
                                          output_path: str) -> pd.DataFrame:
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
    cluster_df = pd.read_csv(cluster_metadata_path,
                             dtype={
                                 "cluster_id": str,
                                 "lead_opinion_id": str
                             })
    llm_outcomes_df = pd.read_csv(llm_outcomes_path, dtype={"opinion_id": str})
    llm_outcomes_df = llm_outcomes_df.rename(
        columns={"model_id": "outcomes_model_id"})
    id_cols = [f"panel_judge_nid_{k}" for k in range(1, 4)]
    judges_df = pd.read_csv(llm_judges_path,
                            dtype={
                                "opinion_id": str,
                                **{
                                    c: "Int64"
                                    for c in id_cols
                                }
                            })
    judges_df = judges_df.rename(columns={"model_id": "judges_model_id"})

    # Merge cluster metadata to LLM-extracted features using lead_opinion_id from cluster metadata
    merged_df = cluster_df.merge(
        llm_outcomes_df,
        left_on="lead_opinion_id",
        right_on="opinion_id",
        how="left",
    )
    merged_df = merged_df.drop(columns=["opinion_id"
                                        ])  # duplicate of lead_opinion_id
    merged_df = merged_df.merge(
        judges_df,
        left_on="lead_opinion_id",
        right_on="opinion_id",
        how="left",
    )
    merged_df = merged_df.drop(columns=["opinion_id"
                                        ])  # duplicate of lead_opinion_id

    # merge FJC full names and characteristics onto each panel judge by judgeship (note party can differ across appointments hence using judgeship instead of judge data)
    judgeships_df = pd.read_csv(JUDGESHIPS_CLEAN_PATH).set_index(
        "judgeship_id")
    for k in range(1, 4):  # merge full name
        merged_df[f"panel_judge_full_name_{k}"] = merged_df[
            f"panel_judgeship_id_{k}"].map(judgeships_df["name_full"])
    # merge demographics
    judge_chars = {
        "rep": "char_rep",
        "dem": "char_dem",
        "female": "char_female",
        "poc": "char_poc"
    }
    for demographic, col_name in judge_chars.items():
        panel_cols = [f"panel_judge_{demographic}_{k}" for k in range(1, 4)]
        for k, panel_col in enumerate(panel_cols, start=1):
            merged_df[panel_col] = merged_df[f"panel_judgeship_id_{k}"].map(
                judgeships_df[col_name])
        # compute case-level counts and existence indicators of demographic vars (missing if not all 3 panel judges are present)
        merged_df[f"count_{demographic}"] = merged_df[panel_cols].sum(
            axis=1, min_count=3)
        merged_df[f"has_{demographic}"] = (
            merged_df[f"count_{demographic}"]
            > 0).astype(float).where(merged_df[f"count_{demographic}"].notna())

    # Save merged data
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(output_path_obj,
                     index=False,
                     quoting=csv.QUOTE_NONNUMERIC)
    print(f"Saved merged data to {output_path_obj}")

    # Print summary statistics
    total_clusters = len(merged_df)

    clusters_with_outcomes = merged_df["prevailing_score"].notna().sum()
    print(f"Total clusters: {total_clusters}")
    print(
        f"Clusters with LLM outcomes: {clusters_with_outcomes} ({clusters_with_outcomes/total_clusters*100:.1f}%)"
    )

    clusters_with_judges = merged_df["panel_judges"].notna().sum()
    print(
        f"Clusters with LLM judges: {clusters_with_judges} ({clusters_with_judges/total_clusters*100:.1f}%)"
    )

    return merged_df


def clean_courtlistener_clusters_main():
    # Find the most recent run directory
    latest_run_dir = get_latest_courtlistener_run()

    cluster_metadata_path = latest_run_dir / "cluster_metadata.csv"
    opinion_metadata_path = latest_run_dir / "opinion_metadata.csv"

    # Clean the data
    clean_cluster_metadata(cluster_metadata_path=str(cluster_metadata_path),
                           opinion_metadata_path=str(opinion_metadata_path),
                           output_path=str(COURTLISTENER_CLUSTER_CLEANED_PATH))

    clean_llm_outcomes(
    )  # save a copy of the LLM-coded outcomes and adds a column for prevailing party

    # Merge LLM-coded outcomes and judges with cluster metadata
    merge_cluster_metadata_w_llm_features(
        cluster_metadata_path=str(COURTLISTENER_CLUSTER_CLEANED_PATH),
        llm_outcomes_path=str(LLM_OPINION_PATH),
        llm_judges_path=str(LLM_JUDGES_PATH),
        output_path=str(COURTLISTENER_METADATA_W_FTRS_PATH))

    print("Done!")


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    clean_courtlistener_clusters_main()
