"""
Clean the Adelman-Glicksman dataset, match it to CourtListener cases by docket number sets, assign validation/test splits, and save train/val/test files.
"""

import csv
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add project root to Python path to allow imports from src.utils
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config import (
    ADELGLICKS_RAW_PATH, ADELGLICKS_SHEET_NAME, ADELGLICKS_CLEANED_PATH,
    COURTLISTENER_CLUSTER_CLEANED_PATH, COURTLISTENER_AG_MATCH_STATS_PATH,
    COURTLISTENER_AG_MATCHING_PATH, COURTLISTENER_AG_MATCHING_SPLIT_PATH,
    FTR_ASSIGNMENTS_DIR, AG_VAL_ASSIGNMENTS_PATH, AG_TEST_ASSIGNMENTS_PATH,
    CL_TRAIN_ASSIGNMENTS_PATH, LLM_OPINION_CLF_RAW_PATH, LLM_OPINION_CLF_PATH,
    LLM_JUDGES_CLF_PATH, CL_TRAIN_PREDICTIONS_PATH)
from utils.case_cleaning_utils import (normalize_dash_characters,
                                       standardize_judge_string,
                                       extract_last_name,
                                       infer_prevailing_party)


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
            df[col] = df[col].apply(lambda x: normalize_dash_characters(x)
                                    if pd.notna(x) else x)

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
    df = df.rename(
        columns={
            "judge_1": "panel_judge_1",
            "judge_2": "panel_judge_2",
            "judge_3": "panel_judge_3",
        })

    # normalize
    df["panel_judge_1"] = standardize_judge_string(df["panel_judge_1"])
    df["panel_judge_2"] = standardize_judge_string(df["panel_judge_2"])
    df["panel_judge_3"] = standardize_judge_string(df["panel_judge_3"])

    # extract last name
    df["panel_judge_1"] = df["panel_judge_1"].apply(extract_last_name)
    df["panel_judge_2"] = df["panel_judge_2"].apply(extract_last_name)
    df["panel_judge_3"] = df["panel_judge_3"].apply(extract_last_name)

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
    clean_adelglicks_data(adelglicks_raw_path=str(ADELGLICKS_RAW_PATH),
                          sheet_name=ADELGLICKS_SHEET_NAME,
                          output_path=str(ADELGLICKS_CLEANED_PATH))


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
            if pd.notna(docket) and str(docket).strip() and str(
                    docket).strip().upper() != 'NAN':
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
        raise ValueError(
            "court_id column not found in CourtListener dataframe")
    if 'court_id' not in ag_df.columns:
        raise ValueError("court_id column not found in AdelGlicks dataframe")

    # Extract docket sets for each row
    print("Extracting docket number sets...")
    cl_docket_sets = cl_df.apply(lambda row: get_docket_set(row),
                                 axis=1)  # pd.Series

    ag_docket_cols = ['docket_no1', 'docket_no2', 'docket_no3']
    ag_docket_sets = ag_df.apply(
        lambda row: get_docket_set(row, ag_docket_cols), axis=1)

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
                        'cluster_id':
                        cl_df.loc[cl_idx, 'cluster_id'],
                        'adelglicks_id':
                        ag_df.loc[ag_idx, 'id_num'],
                        'court_id':
                        cl_df.loc[cl_idx, 'court_id'],
                        'CL_year_filed':
                        cl_df.loc[cl_idx, 'year_filed'],
                        'AG_year_filed':
                        ag_df.loc[ag_idx, 'year_filed'],
                        'CL_AG_year_match':
                        (cl_df.loc[cl_idx,
                                   'year_filed'] == ag_df.loc[ag_idx,
                                                              'year_filed']),
                        'year_filed_diff': (cl_df.loc[cl_idx, 'year_filed'] -
                                            ag_df.loc[ag_idx, 'year_filed']),
                        'CL_docket_count':
                        len(cl_dockets),
                        'AG_docket_count':
                        len(ag_dockets),
                        'overlap_count':
                        len(overlap),
                        'CL_dockets':
                        "; ".join(sorted(cl_dockets)),
                        'AG_dockets':
                        "; ".join(sorted(ag_dockets)),
                        'overlapping_dockets':
                        "; ".join(sorted(overlap)),
                        'AG_has_outcome':
                        (pd.notna(ag_df.loc[ag_idx, 'district_outcome'])
                         and pd.notna(ag_df.loc[ag_idx, 'disposition'])),
                        'is_perfect_match':
                        cl_dockets == ag_dockets,
                        'CL_subset_of_AG':
                        cl_dockets.issubset(ag_dockets),
                        'AG_subset_of_CL':
                        ag_dockets.issubset(cl_dockets),
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
        cl_counts.gt(1)).fillna(False)
    matches_df['AG_has_multiple_matches'] = matches_df['adelglicks_id'].map(
        ag_counts.gt(1)).fillna(False)

    return matches_df


def compute_match_statistics(cl_df, ag_df, matches_df, cl_docket_sets,
                             ag_docket_sets):
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
        stats['cl_strict_subset_of_ag'] = stats['cl_subset_of_ag'] - stats[
            'perfect_matches']
        stats['ag_strict_subset_of_cl'] = stats['ag_subset_of_cl'] - stats[
            'perfect_matches']

        # Multiple match statistics
        cl_match_counts = matches_df.groupby('cluster_id').size()
        ag_match_counts = matches_df.groupby('adelglicks_id').size()
        stats['cl_cases_with_multiple_matches'] = (cl_match_counts > 1).sum()
        stats['ag_cases_with_multiple_matches'] = (ag_match_counts > 1).sum()

        # Perfect matches that also have multiple matches
        cl_perfect_any = matches_df[matches_df['is_perfect_match']].groupby(
            'cluster_id').size()
        ag_perfect_any = matches_df[matches_df['is_perfect_match']].groupby(
            'adelglicks_id').size()
        stats['cl_cases_perfect_and_multiple'] = (
            cl_perfect_any.reindex(cl_match_counts.index, fill_value=0).gt(0)
            & cl_match_counts.gt(1)).sum()
        stats['ag_cases_perfect_and_multiple'] = (
            ag_perfect_any.reindex(ag_match_counts.index, fill_value=0).gt(0)
            & ag_match_counts.gt(1)).sum()

        # Overlap count distribution
        stats['overlap_distribution'] = matches_df[
            'overlap_count'].value_counts().to_dict()

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
    stats['cl_cases_unmatched'] = stats['total_cl_cases'] - stats[
        'unique_cl_matched']
    stats['ag_cases_unmatched'] = stats['total_ag_cases'] - stats[
        'unique_ag_matched']

    return stats


def _format_merge_statistics(stats):
    """Format match statistics in a readable format."""
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("DOCKET NUMBER MATCH STATISTICS")
    lines.append("=" * 60)

    lines.append("\nDataset Overview:")
    lines.append(f"  CourtListener cases: {stats['total_cl_cases']}")
    lines.append(f"  AdelGlicks cases: {stats['total_ag_cases']}")

    lines.append("\nMatch Overview:")
    lines.append(f"  Total matches found: {stats['total_matches']}")
    lines.append(
        f"  Unique CourtListener cases matched: {stats['unique_cl_matched']}")
    lines.append(
        f"  Unique AdelGlicks cases matched: {stats['unique_ag_matched']}")
    lines.append(
        f"  CourtListener cases unmatched: {stats['cl_cases_unmatched']}")
    lines.append(
        f"  AdelGlicks cases unmatched: {stats['ag_cases_unmatched']}")

    if stats['total_matches'] > 0:
        lines.append("\nMultiple Match Statistics:")
        lines.append(
            f"  CL cases with multiple matches: {stats['cl_cases_with_multiple_matches']}"
        )
        lines.append(
            f"  AG cases with multiple matches: {stats['ag_cases_with_multiple_matches']}"
        )
        lines.append(
            f"  CL cases perfect + multiple: {stats['cl_cases_perfect_and_multiple']}"
        )
        lines.append(
            f"  AG cases perfect + multiple: {stats['ag_cases_perfect_and_multiple']}"
        )

        lines.append("\nMatch Quality:")
        lines.append(
            f"  Perfect matches (identical docket sets): {stats['match_quality'].get('perfect', 0)}"
        )
        lines.append(
            f"  CL strict subset of AG (all CL dockets in AG): {stats['match_quality'].get('cl_strict_subset', 0)}"
        )
        lines.append(
            f"  AG strict subset of CL (all AG dockets in CL): {stats['match_quality'].get('ag_strict_subset', 0)}"
        )
        lines.append(
            f"  Partial matches (some overlap): {stats['match_quality'].get('partial', 0)}"
        )

        lines.append("\nOverlap Count Distribution:")
        for overlap_count, match_count in sorted(
                stats['overlap_distribution'].items()):
            lines.append(
                f"  {overlap_count} docket(s) overlap: {match_count} matches")

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
    matches_df, cl_docket_sets, ag_docket_sets = compute_all_matches(
        cl_df, ag_df)
    matches_df = find_cases_with_multiple_matches(matches_df)

    # Compute statistics
    stats = compute_match_statistics(cl_df, ag_df, matches_df, cl_docket_sets,
                                     ag_docket_sets)

    # Print statistics and save to text file
    stats_output = _print_merge_statistics(stats)
    COURTLISTENER_AG_MATCH_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COURTLISTENER_AG_MATCH_STATS_PATH.write_text(stats_output,
                                                 encoding="utf-8")

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

    unmatched_cl = cl_df[~cl_df["cluster_id"].isin(matches_df["cluster_id"]
                                                   )].copy()
    unmatched_cl = unmatched_cl[~unmatched_cl["cluster_id"].isin(exclude_ids)]

    # Build rows with same columns as matches_df
    base_cols = list(matches_df.columns)
    cl_train_unmatched = pd.DataFrame(columns=base_cols)
    cl_train_unmatched["cluster_id"] = unmatched_cl["cluster_id"]
    cl_train_unmatched["court_id"] = unmatched_cl["court_id"]
    cl_train_unmatched["CL_year_filed"] = unmatched_cl["year_filed"]
    cl_train_unmatched["dataset_split"] = "train"

    cl_train_df = pd.concat([train_matches, cl_train_unmatched],
                            ignore_index=True)

    # Save output
    CL_TRAIN_ASSIGNMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    cl_train_df.to_csv(CL_TRAIN_ASSIGNMENTS_PATH, index=False)
    print(f"Saved CL train set to: {CL_TRAIN_ASSIGNMENTS_PATH}")


def assign_val_test_split_main():
    matches_df = pd.read_csv(COURTLISTENER_AG_MATCHING_PATH)
    matches_df = assign_val_test_split(matches_df)

    # Save outputs
    COURTLISTENER_AG_MATCHING_SPLIT_PATH.parent.mkdir(parents=True,
                                                      exist_ok=True)
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
    train_assignments = pd.read_csv(train_assignments_path,
                                    dtype={"cluster_id": str})
    cl_df = pd.read_csv(COURTLISTENER_CLUSTER_CLEANED_PATH,
                        dtype={
                            "cluster_id": str,
                            "lead_opinion_id": str
                        })
    pred_outcomes_df = pd.read_csv(LLM_OPINION_CLF_PATH,
                                   dtype={"opinion_id": str})
    pred_outcomes_df = pred_outcomes_df.rename(
        columns={"model_id": "outcomes_model_id"})
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
    merged = merged.drop(columns=["opinion_id"
                                  ])  # duplicate of lead_opinion_id
    merged = merged.merge(
        judges_df,
        left_on="lead_opinion_id",
        right_on="opinion_id",
        how="left",
    )
    merged = merged.drop(columns=["opinion_id"
                                  ])  # duplicate of lead_opinion_id

    merged = merged.rename(
        columns={
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
    print(
        f"Cases with predictions: {cases_with_predictions} ({cases_with_predictions/total_cases*100:.1f}%)"
    )

    cases_with_judges = merged["panel_judges"].notna().sum()
    print(
        f"Cases with judges: {cases_with_judges} ({cases_with_judges/total_cases*100:.1f}%)"
    )

    return merged


def flip_district_outcome(
    input_path: Path = LLM_OPINION_CLF_RAW_PATH, ) -> pd.DataFrame:
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
        "defendant":
        "plaintiff",
        "plaintiff":
        "defendant",
    }).fillna(
        df["district_outcome"]
    )  # Keep original value if not in mapping (e.g., "mixed", "UNK", NaN)

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
    merge_cases_by_docket_main()
    assign_val_test_split_main()
    # flip_district_outcome() # temporary workaround because it seems like the LLM coded everything the opposite way
    merge_cl_train_w_llm_features(
    )  # saves a copy of courtlistener data excluded from the val/test sets and merges with predictions


if __name__ == "__main__":
    main()
