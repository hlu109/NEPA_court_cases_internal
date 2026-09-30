"""
Clean and process judge data from the FJC.
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to Python path to allow imports from src.utils
project_root = Path(__file__).parents[2]
sys.path.insert(0, str(project_root))

from utils.config import FJC_RAW_DIR, JUDGESHIPS_CLEAN_PATH
from utils.judge_names import normalize_last_name, clean_name_string

# indicator columns for race/ethnicity
RACE_IND_COLS = [
    "char_white", "char_black", "char_hispanic", "char_asian",
    "char_other_race"
]


def fjc_court_to_courtlistener_id(name) -> str:
    """Map an FJC court name to the CourtListener court id."""
    circuit_ordinals = {
        "First": "ca1",
        "Second": "ca2",
        "Third": "ca3",
        "Fourth": "ca4",
        "Fifth": "ca5",
        "Sixth": "ca6",
        "Seventh": "ca7",
        "Eighth": "ca8",
        "Ninth": "ca9",
        "Tenth": "ca10",
        "Eleventh": "ca11",
        "District of Columbia": "cadc",
        "Federal": "cafc",
    }

    if name == "Supreme Court of the United States":
        return "scotus"

    m = re.match(r"U\.S\. Court of Appeals for the (.+) Circuit$", str(name))
    # note district courts get dropped
    return circuit_ordinals.get(m.group(1), "") if m else ""


def main():
    # TODO: add rest of demographic variables
    fjc_demographics = pd.read_csv(FJC_RAW_DIR / "demographics.csv", dtype=str)
    fjc_service = pd.read_csv(FJC_RAW_DIR / "federal-judicial-service.csv",
                              dtype=str)
    fjc_education = pd.read_csv(FJC_RAW_DIR / "education.csv", dtype=str)
    fjc_career = pd.read_csv(FJC_RAW_DIR / "professional-career.csv",
                             dtype=str)
    fjc_other_service = pd.read_csv(FJC_RAW_DIR /
                                    "other-federal-judicial-service.csv",
                                    dtype=str)

    # construct dataframe of judgeships (can have multiple appointments for the same judge over time)
    judgeships = pd.DataFrame({
        "fjc_nid": fjc_service["nid"],
        "appointment_seq": fjc_service["Sequence"].astype(int),
        "court_type": fjc_service["Court Type"],
        "court_name": fjc_service["Court Name"],
        "appointing_pres": fjc_service["Appointing President"],
        "appointing_party": fjc_service["Party of Appointing President"],
    })
    # create unique row ids
    judgeships["judgeship_id"] = judgeships["fjc_nid"] + "_" + judgeships[
        "appointment_seq"].astype(str)
    # map the court name to the CourtListener court id
    judgeships["court_id"] = judgeships["court_name"].map(
        fjc_court_to_courtlistener_id)

    # add in date variables
    judgeships = judgeships.assign(
        date_recess_appt=pd.to_datetime(fjc_service["Recess Appointment Date"],
                                        errors="coerce"),
        date_commission=pd.to_datetime(fjc_service["Commission Date"],
                                       errors="coerce"),
        date_termination=pd.to_datetime(fjc_service["Termination Date"],
                                        errors="coerce"),
    )

    # handle recess appointments, make sure the start date is correct if the recess appt gets converted to a confirmed appointment
    judgeships["date_service_start"] = judgeships[[
        "date_recess_appt", "date_commission"
    ]].min(axis=1)

    # handle judgeships reassigned by statute to inherit the appointer of the judge's previous judgeship since they have no appointing president (mainly consequential for 11th circuit being split from the 5th circuit in 1981)
    judgeships = judgeships.sort_values(["fjc_nid", "appointment_seq"])
    no_appointer = judgeships["appointing_pres"].fillna("").str.startswith(
        "None")  # check if the appointing president is missing
    judgeships["appointer_inherited"] = no_appointer.astype(int)
    for col in ["appointing_pres", "appointing_party"]:
        judgeships[col] = judgeships[col].mask(no_appointer)
        judgeships[col] = judgeships.groupby("fjc_nid")[col].ffill(
        )  # forward fill from the last non-missing value within the judge id group

    # party indicators (missing when FJC has no appointing party)
    has_party = judgeships["appointing_party"].notna()
    judgeships["char_rep"] = (judgeships["appointing_party"] == "Republican"
                              ).astype(float).where(has_party)
    judgeships["char_dem"] = (judgeships["appointing_party"] == "Democratic"
                              ).astype(float).where(has_party)

    # determine whether the judge was formerly a federal prosecutor before starting their judgeship
    career = pd.DataFrame({
        "fjc_nid": fjc_career["nid"],
        "text": fjc_career["Professional Career"].fillna("")
    })
    # extract the first year that appears in the text string (usually has the format "start year - end year")
    career["start_year"] = pd.to_numeric(
        career["text"].str.extract(r"\b(1[6-9]\d\d|20\d\d)\b")[0],
        errors="coerce")
    # patterns for federal prosecutor roles - assistant us attorney, us attorney
    fedpros_patterns = {
        "char_fedpros_ausa": r"(?i)\b(assistant|deputy)\s+U\.S\.\s+attorney|assistant United States attorney",
        "char_fedpros_usa": r"(?i)(?<!assistant )(?<!deputy )\bU\.S\.\s+attorney\b(?! general)",
    }
    for col, pattern in fedpros_patterns.items():
        career[col] = career["text"].str.contains(pattern)

    judgeships["appointment_year"] = judgeships["date_service_start"].dt.year
    career = judgeships[["judgeship_id", "fjc_nid",
                         "appointment_year"]].merge(career,
                                                    on="fjc_nid",
                                                    how="left")
    # check if the federal prosecutor role started before the judgeship (if the year is missing, assume it counts for now)
    prior = (career["start_year"]
             <= career["appointment_year"]) | career["start_year"].isna()
    fedpros_cols = list(fedpros_patterns)
    for col in fedpros_cols:
        career[col] = (career[col].fillna(False) & prior).astype(int)
    # construct single umbrella flag against all federal prosecutor roles
    fedpros = career.groupby("judgeship_id")[fedpros_cols].max()
    fedpros["char_fedpros"] = fedpros[fedpros_cols].max(axis=1)
    judgeships = judgeships.merge(fedpros, on="judgeship_id", how="left")

    # get demographic data
    demo = pd.DataFrame({
        "fjc_nid": fjc_demographics["nid"],
        "name_first": fjc_demographics["First Name"].fillna(""),
        "name_middle": fjc_demographics["Middle Name"].fillna(""),
        "name_last": fjc_demographics["Last Name"].map(normalize_last_name),
        "name_suffix": fjc_demographics["Suffix"].fillna("").str.strip(),
        "birth_year": pd.to_numeric(fjc_demographics["Birth Year"],
                                    errors="coerce").astype("Int64"),
        "death_year": pd.to_numeric(fjc_demographics["Death Year"],
                                    errors="coerce"),
        "gender": fjc_demographics["Gender"],
        "race_raw": fjc_demographics["Race or Ethnicity"],
    })

    # reconstruct full name for display purposes
    name_parts = fjc_demographics[[
        "First Name", "Middle Name", "Last Name", "Suffix"
    ]].fillna("")
    demo["name_full"] = name_parts.apply(" ".join,
                                         axis=1).map(clean_name_string)

    # gender indicator
    has_gender = demo["gender"].isin(["Male", "Female"])
    demo["char_female"] = (
        demo["gender"] == "Female").astype(float).where(has_gender)

    has_race = demo["race_raw"].notna() & (demo["race_raw"]
                                           != "Declined to Report")
    race_entries = demo["race_raw"].fillna("").str.split("/")

    # map from FJC race/ethnicity to indicator columns
    race_map = {
        "White": ["char_white"],
        "Portuguese": ["char_white"],
        "African American": ["char_black"],
        "Afro-Latino": ["char_black", "char_hispanic"],
        "Hispanic": ["char_hispanic"],
        "Latino": ["char_hispanic"],
        "Cuban American": ["char_hispanic"],
        "Asian American": ["char_asian"],
        "Korean American": ["char_asian"],
        "South Asian American": ["char_asian"],
        "Pakistani": ["char_asian"],
    }  # note anything not caught here (e.g. American Indian, Pacific Islander, Middle Eastern, Chaldean, Caribbean American, Other) maps to char_other_race

    for col in RACE_IND_COLS:
        demo[col] = 0.0  # set as float to be consistent with missing values
    for i, parts in race_entries.items():
        for part in parts:
            part = part.strip()
            if not part:
                continue
            for col in race_map.get(part, ["char_other_race"]):
                demo.at[i, col] = 1
    demo.loc[~has_race, RACE_IND_COLS] = np.nan

    # indicator for person of color (note this includes people who are Hispanic/White, the FJC coding is ambiguous as to whether they are mixed race or if they are Spanish White)
    demo["char_poc"] = demo[[
        "char_black", "char_hispanic", "char_asian", "char_other_race"
    ]].max(axis=1)

    # merge demographic data onto judgeships
    judgeships = judgeships.merge(demo, on="fjc_nid", how="left")

    # filter judges to only those active after NEPA
    cutoff = pd.Timestamp("1970-01-01")
    still_serving = judgeships["date_termination"].isna() & (
        judgeships["death_year"].isna()
        | (judgeships["death_year"] >= cutoff.year))
    keep = (judgeships["date_termination"] >= cutoff) | still_serving
    judgeships = judgeships[keep].copy()

    # select columns for export
    id_cols = [
        "judgeship_id", "fjc_nid", "court_id", "court_type", "court_name",
        "appointment_seq", "name_first", "name_middle", "name_last",
        "name_suffix", "name_full", "date_service_start", "date_termination"
    ]
    party_cols = [
        "appointing_pres", "appointing_party", "appointer_inherited",
        "char_rep", "char_dem"
    ]
    race_cols = ["race_raw"] + RACE_IND_COLS + ["char_poc"]
    demo_cols = ["birth_year", "gender", "char_female"]
    career_cols = ["char_fedpros", "char_fedpros_ausa", "char_fedpros_usa"]
    judgeships = judgeships[id_cols + party_cols + race_cols + demo_cols +
                            career_cols]

    # reformat date variables for export
    for col in ["date_service_start", "date_termination"]:
        judgeships[col] = judgeships[col].dt.strftime("%Y-%m-%d")

    # export data
    JUDGESHIPS_CLEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    judgeships.sort_values(["name_last", "fjc_nid",
                            "appointment_seq"]).to_csv(JUDGESHIPS_CLEAN_PATH,
                                                       index=False)

    print(f"Judgeships table exported to {JUDGESHIPS_CLEAN_PATH}")


if __name__ == "__main__":
    main()
    print("******************\nScript complete.\n******************")
