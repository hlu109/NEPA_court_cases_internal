"""
Helper functions to clean court case data.
"""

import pandas as pd

from utils.config import USGOV_PL_PATH, COURTLISTENER_RAW_DIR


def normalize_dash_characters(text: str) -> str:
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
    df.loc[df['disposition'] == 'affirm',
           'prevailing_party'] = df['district_outcome']
    # if disposition is reverse, then prevailing party = opposite of district outcome
    df.loc[df['disposition'] == 'reverse',
           'prevailing_party'] = df['district_outcome'].map(
               lambda x: 'defendant' if x == 'plaintiff' else 'plaintiff'
               if x == 'defendant' else None)
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
    usgov_pl_df = pd.read_csv(
        USGOV_PL_PATH, encoding="latin-1"
    )  # utf-8 encoding doesn't work for some reason (can't decode byte 0xd5 in position 47954)

    # get everything where the US government is the plaintiff. ignore the stuff Maggie says to drop from analysis. don't touch the stuff where gov losing is pro-development.
    opinion_ids_to_flip = usgov_pl_df.loc[(
        (usgov_pl_df["include_in_analysis"] == 1) &
        (usgov_pl_df["gov_losing_as_pro_dev"] != 1)), "opinion_id"].unique()
    # flip the mapping for these specific cases
    flip_mask = df["opinion_id"].isin(opinion_ids_to_flip)
    df.loc[flip_mask,
           "pro_dev_district_score"] = df.loc[flip_mask,
                                              "district_outcome"].map({
                                                  "defendant": 0,
                                                  "plaintiff": 1,
                                                  "mixed": 0.5,
                                                  "UNK": None,
                                              })
    df.loc[flip_mask,
           "pro_dev_prevailing_score"] = df.loc[flip_mask,
                                                "prevailing_party"].map({
                                                    "defendant": 0,
                                                    "plaintiff": 1,
                                                    "mixed": 0.5,
                                                    "UNK": None,
                                                })
    return df


def get_latest_courtlistener_run():
    """Returns the most recent CourtListener download folder (run_YYYYMMDD_HHMMSS) in COURTLISTENER_RAW_DIR."""
    run_dirs = sorted([
        d for d in COURTLISTENER_RAW_DIR.iterdir()
        if d.is_dir() and d.name.startswith("run_")
    ])
    if not run_dirs:
        raise FileNotFoundError(
            f"No run directories found in {COURTLISTENER_RAW_DIR}")
    latest_run_dir = run_dirs[-1]
    print(f"Using CourtListener run: {latest_run_dir.name}")
    return latest_run_dir
