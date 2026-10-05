"""
Parse the judge names in the Gemini case data, match each name to an FJC judgeship, and construct a crosswalk between cases and judges. Also run match diagnostics. 
"""

import difflib  # for basic fuzzy matching
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to Python path to allow imports from src.utils
project_root = Path(__file__).parents[2]
sys.path.insert(0, str(project_root))

from utils.config import (LLM_JUDGES_RAW_PATH, LLM_JUDGES_PATH,
                          JUDGESHIPS_CLEAN_PATH, JUDGE_CASE_CROSSWALK_PATH,
                          JUDGE_MATCH_SUMMARY_PATH, NAME_TYPO_REVIEW_PATH)
from utils.judge_names import (parse_judge_name, clean_name_string,
                               standardize_judges_raw, SUFFIXES)
from utils.case_cleaning_utils import get_latest_courtlistener_run

N_WIDE_PANEL_JUDGES = 3  # number of judges to keep in wide case-level file


def _fjc_given_names(first: str, middle: str) -> tuple:
    """Cleans and extracts given names for an FJC judge. Handles bracketed names (e.g. "N[orman]" -> "NORMAN" and "N").
    
    Returns:
        tuple of two sets, full given names and initials
    """
    text = clean_name_string(
        f"{first} {middle}")  # this also drops punctuation
    names = text.split()
    full_names = {n for n in names if len(n) > 1}
    initials = {n[0] for n in names}
    return full_names, initials


def match_judge(court_id, last, date, first, middle,
                judges_by_last_name: dict) -> dict:
    """
    Match a single judge from a court case to FJC records.

    Filters FJC records by same court, last name, and active status at the date of filing the opinion. 

    Note: For now we only match by last name and consider a match if there is a unique candidate from the FJC records. If there are multiple candidates we mark the attempt as ambiguous for now. 

    TODO: (phase 1b) Implement further refinement of the matching by first and middle names. 
    TODO: (phase 2) Handle visiting judges. 
    TODO: (phase 2) Handle name changes.

    Args:
        * court_id (str): CourtListener court id of the case.
        * last (str): standardized last name as extracted from the case.
        * date (pd.Timestamp): opinion filing date of the case.
        * first (str): first name or initial as extracted from the case.
        * middle (str): other given names or initials as extracted from the case.
        * judges_by_last_name (dict): pre-constructed lookup directory of judgeships keyed on (court_id, last name).

    Returns:
        Dict with match_status, match_method, n_candidates, candidate_nids, and the matched judgeship row if successful.
    """
    result = {
        "match_status": "unmatched",
        "match_method": "",
        "n_candidates": 0,
        "candidate_nids": "",
        "judgeship": None
    }
    if pd.isna(date) or pd.isna(court_id):
        return result

    # 1. filter candidates by last name, court, and active status
    active = [
        record for record in judges_by_last_name.get((court_id, last), [])
        if record["date_service_start"] <= date and (pd.isna(
            record["date_termination"]) or record["date_termination"] >= date)
    ]
    candidates = {
        record["fjc_nid"]: record
        for record in active
    }  # dict of records keyed by the FJC id
    result["n_candidates"] = len(candidates)
    result["candidate_nids"] = ";".join(sorted(candidates))
    method = "last_name"

    # 2. tie-breaking rules, applied in order only while more than one candidate remains
    # TODO (phase 1b): ranked match by first and middle names
    # TODO (phase 2): visiting judges

    # 3. result
    if len(candidates) == 1:
        result.update({
            "match_status": "matched",
            "match_method": method,
            "judgeship": next(iter(candidates.values())),
        })
    elif len(candidates) > 1:
        result.update({"match_status": "ambiguous", "match_method": method})
    return result


def main():
    # ------------------------------------------------------------------
    # load data
    # ------------------------------------------------------------------

    # load raw judge names extracted by Gemini
    gemini = pd.read_csv(LLM_JUDGES_RAW_PATH)
    gemini = gemini.drop(
        columns=["district_outcome", "disposition"],
        errors="ignore")  # drop the outcome coding, we handle that later

    # load courtlistener data
    latest_run_dir = get_latest_courtlistener_run()
    clusters = pd.read_csv(latest_run_dir / "cluster_metadata.csv",
                           usecols=["cluster_id", "court_id", "dateFiled"])
    clusters = clusters.drop_duplicates()
    assert clusters[
        "cluster_id"].is_unique, "conflicting court/date rows for the same cluster_id"
    opinions = pd.read_csv(latest_run_dir / "opinion_metadata.csv",
                           usecols=["opinion_id", "cluster_id"])
    opinions = opinions.drop_duplicates()
    assert opinions[
        "opinion_id"].is_unique, "opinion_id mapped to more than one cluster_id"

    # map opinions (which contain judge names extracted by Gemini) to clusters so we can look up court and filing date
    opinion_to_cluster = opinions.set_index("opinion_id")["cluster_id"]

    # load FJC judgeships
    judgeships = pd.read_csv(JUDGESHIPS_CLEAN_PATH,
                             dtype={"fjc_nid": str},
                             keep_default_na=True)
    for col in ["date_service_start", "date_termination"]:
        judgeships[col] = pd.to_datetime(judgeships[col])
    judgeships[["name_first",
                "name_middle"]] = judgeships[["name_first",
                                              "name_middle"]].fillna("")

    # ------------------------------------------------------------------
    # clean judge names extracted by Gemini
    # ------------------------------------------------------------------
    panel = standardize_judges_raw(gemini["panel_judges"])
    authors = standardize_judges_raw(gemini["opinion_authors"])

    # flag en banc panels and per curiam opinions, then remove the text from the name lists
    gemini["en_banc"] = panel.str.contains("EN BANC", regex=False).astype(int)
    gemini["per_curiam"] = authors.str.contains("PER CURIAM",
                                                regex=False).astype(int)
    panel = panel.str.replace("EN BANC", "", regex=False)
    authors = authors.str.replace("PER CURIAM", "",
                                  regex=False).str.replace("EN BANC",
                                                           "",
                                                           regex=False)
    # split the semicolon-delimited string into list of judges
    panel_names = panel.str.split("; ")

    # ------------------------------------------------------------------
    # convert data to judge x case appearances
    # ------------------------------------------------------------------

    appearances = []
    for opinion_id, names in zip(gemini["opinion_id"], panel_names):
        for panel_order, name_raw in enumerate(names, start=1):
            cluster_id = opinion_to_cluster.get(opinion_id)
            appearances.append((panel_order, opinion_id, cluster_id, name_raw))
    mentions = pd.DataFrame(
        appearances,
        columns=["panel_order", "opinion_id", "cluster_id", "name_raw"])

    # parse each name into first, middle, suffix and last name
    parsed = pd.DataFrame([parse_judge_name(n) for n in mentions["name_raw"]])
    mentions["name_first"] = parsed["first"]
    mentions["name_middle"] = parsed["middle"]
    mentions["name_suffix"] = parsed["suffix"]
    mentions["name_last"] = parsed["last"]

    # attach the case's court and filing date
    case_info = clusters.set_index("cluster_id")  # convert to lookup table
    mentions["court_id"] = mentions["cluster_id"].map(case_info["court_id"])
    mentions["date_filed"] = pd.to_datetime(mentions["cluster_id"].map(
        case_info["dateFiled"]),
                                            errors="coerce")

    # drop entries that are not names (empty strings; "UNK" also gets parsed as empty for all name fields)
    mentions = mentions[mentions["name_last"] != ""].reset_index(drop=True)

    # ------------------------------------------------------------------
    # match each judge on every case to an FJC judgeship
    # ------------------------------------------------------------------
    # construct a lookup directory of appellate and Supreme Court judgeships indexed by (court, last name)
    judges_by_last_name = {}
    for r in judgeships[judgeships["court_id"].notna()].to_dict("records"):
        # if the court x last name combo isn't seen yet in our lookup dict, add it as a new key, initiate the value as an empty list, and insert the judgeship record (itself a dict); if the combo already exists, just append it to the existing list of records
        judges_by_last_name.setdefault((r["court_id"], r["name_last"]),
                                       []).append(r)

    # get match results
    results = [
        match_judge(r.court_id, r.name_last, r.date_filed, r.name_first,
                    r.name_middle, judges_by_last_name)
        for r in mentions.itertuples()
    ]
    matched = mentions.copy()
    for col in [
            "match_status", "match_method", "n_candidates", "candidate_nids"
    ]:
        matched[col] = [r[col] for r in results]

    # merge the qualifying judgeship info into the matched dataframe
    matched_rows_temp = pd.DataFrame([r["judgeship"] or {} for r in results],
                                     index=matched.index)
    for col in ["judgeship_id", "fjc_nid"]:
        matched[col] = matched_rows_temp[
            col] if col in matched_rows_temp else np.nan

    # export judge-case crosswalk
    crosswalk = matched.copy()
    crosswalk["date_filed"] = crosswalk["date_filed"].dt.strftime("%Y-%m-%d")
    JUDGE_CASE_CROSSWALK_PATH.parent.mkdir(parents=True, exist_ok=True)
    crosswalk.to_csv(JUDGE_CASE_CROSSWALK_PATH, index=False)
    print(f"Exported judge-case crosswalk to {JUDGE_CASE_CROSSWALK_PATH}")

    # also export a wide version of the crosswalk indexed at the opinion level for downstream merging and analysis
    # keep the raw Gemini judge columns plus en_banc and per_curiam, then adds last names, FJC ids and match status for each panel position
    wide = gemini.copy()
    by_panel_order = matched.set_index(["opinion_id", "panel_order"])

    def _panel_values(col, k, fill):
        # value of col for the k-th listed panel judge in each opinion
        idx = pd.MultiIndex.from_arrays([wide["opinion_id"], [k] * len(wide)])
        return by_panel_order[col].reindex(idx).fillna(fill).values

    for k in range(1, N_WIDE_PANEL_JUDGES + 1):
        wide[f"panel_judge_{k}"] = _panel_values("name_last", k, "")
        wide[f"panel_judge_first_{k}"] = _panel_values("name_first", k, "")
        wide[f"panel_judge_middle_{k}"] = _panel_values("name_middle", k, "")
        wide[f"panel_judge_suffix_{k}"] = _panel_values("name_suffix", k, "")
        wide[f"panel_judge_nid_{k}"] = _panel_values("fjc_nid", k, np.nan)
        wide[f"panel_judgeship_id_{k}"] = _panel_values(
            "judgeship_id", k, np.nan)
        wide[f"panel_judge_match_{k}"] = _panel_values("match_status", k,
                                                       np.nan)

    # flag opinions where every listed panel judge is matched to a unique FJC judge
    n_matched = wide["opinion_id"].map(
        matched[matched["match_status"] == "matched"].groupby(
            "opinion_id").size()).fillna(0)
    wide["panel_all_matched"] = (
        (wide["panel_judge_count"] > 0) &
        (n_matched == wide["panel_judge_count"])).astype(int)

    # export
    LLM_JUDGES_PATH.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(LLM_JUDGES_PATH, index=False)
    print(f"Saved cleaned Gemini judge file to {LLM_JUDGES_PATH}")


if __name__ == "__main__":
    main()
    print("******************\nScript complete.\n******************")
