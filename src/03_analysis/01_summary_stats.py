"""
Compute basic summary statistics from LLM opinion coding data.
"""

import pandas as pd
from pathlib import Path

from utils.config import (
    LLM_OPINION_CLF_PATH,
    INTERMEDIATE_DATA_DIR,
)


def compute_frequency_counts(df: pd.DataFrame, variable: str) -> pd.Series:
    """
    Compute frequency counts for a given variable.
    
    Args:
        df: DataFrame containing the data
        variable: Name of the variable/column to compute frequencies for
        
    Returns:
        Series with value counts (sorted by count descending)
    """
    return df[variable].value_counts().sort_values(ascending=False)


def main():
    """
    Load LLM opinion coding data and compute frequency counts for each variable.
    """
    print(f"Loading data from: {LLM_OPINION_CLF_PATH}")
    df = pd.read_csv(LLM_OPINION_CLF_PATH, dtype={"opinion_id": str})

    print(f"\nTotal observations: {len(df)}")
    print(f"\nColumns: {', '.join(df.columns.tolist())}")

    # Variables to compute frequencies for
    categorical_vars = ["district_outcome", "disposition", "prevailing_party"]

    # Check which variables exist in the dataframe
    available_vars = [var for var in categorical_vars if var in df.columns]
    missing_vars = [var for var in categorical_vars if var not in df.columns]

    if missing_vars:
        print(
            f"\nWarning: The following variables were not found in the data: {', '.join(missing_vars)}"
        )

    # Compute and print frequency counts for each variable
    results = {}
    for var in available_vars:
        counts = compute_frequency_counts(df, var)
        results[var] = counts

    # Save results to CSV
    output_dir = INTERMEDIATE_DATA_DIR / "Summary Statistics"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "llm_opinion_coding_frequencies.csv"

    # Combine all results into a single dataframe for saving
    summary_rows = []
    for var, counts in results.items():
        for label, count in counts.items():
            percentage = (count / len(df)) * 100
            summary_rows.append({
                "variable": var,
                "label": label,
                "count": count,
                "percentage": percentage
            })

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(output_path, index=False)
    print(f"\n\nSaved summary statistics to: {output_path}")

    return summary_df


if __name__ == "__main__":
    main()
