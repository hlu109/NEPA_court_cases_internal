"""
Helper functions to clean and standardize judge names.
"""

import re
import unicodedata
import pandas as pd

SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}

LAST_NAME_PARTICLES = {
    "VAN", "VON", "DER", "DE", "DEL", "DELLA", "DI", "DA", "DU", "LA", "LE",
    "ST", "SAINT", "TEN", "TER"
}

LAST_NAME_TYPOS = {
    "TYMKOVCH": "TYMKOVICH",
    "SCANNLAIN": "OSCANNLAIN",
    "FUST": "FUSTE",
    "ALARC": "ALARCON",
    "MCCOWAN": "MCGOWAN",
    "OUSCANNLAIN": "OSCANNLAIN",
    # CourtListener's judge strings sometimes drop "Van"
    "GRAAFEILAND": "VANGRAAFEILAND",
    "DUSEN": "VANDUSEN",
    "OOSTERHOUT": "VANOOSTERHOUT",
    "PELT": "VANPELT",
    "ANTWERPEN": "VANANTWERPEN",
}


def standardize_judges_raw(judge_series: pd.Series) -> pd.Series:
    """Standardize raw judge text by filling missing values with empty strings, stripping whitespace, and converting to uppercase."""
    return judge_series.fillna("").astype(str).str.strip().str.upper()


def clean_name_string(raw) -> str:
    """
    Clean encoding artifacts, removes punctuation, and collapses whitespace in a name string.
    """
    if not isinstance(raw, str):  # handle missing values (NaNs)
        return ""
    s = raw.upper().strip()

    # handle character encoding issues
    # e.g. ALARCÃ“N -> ALARCON, DUHÃ‰ -> DUHÉ
    s = s.replace("Ã“", "O")
    s = s.replace("Ã‰", "E")

    # replace accented characters with their non-accented ASCII letters
    s = unicodedata.normalize("NFKD", s).encode("ascii",
                                                "ignore").decode("ascii")

    # drop punctuation except commas
    s = s.replace(".", " ")
    s = re.sub(r"[^\w\s,]", "", s)

    # collapse whitespace
    return re.sub(r"\s+", " ", s).strip()


def normalize_last_name(last) -> str:
    key = clean_name_string(last)
    key = re.sub(r"[^A-Z]", "", key)  # drop non-alphabetic characters
    return LAST_NAME_TYPOS.get(key, key)  # correct typos


def parse_judge_name(raw) -> dict:
    """
    Split a judge name into given names, last name and suffix.

    Returns:
        * Dict with keys for first, middle, last, and suffix.
    """
    s = clean_name_string(raw)
    parsed = {"first": "", "middle": "", "suffix": "", "last": ""}
    if not s or s == "UNK":
        return parsed

    # split name on comma, which can denote last, first format or first middle last, suffix format
    parts = [p.strip() for p in s.split(",") if p.strip()]
    suffix = ""
    rest = []  # non-suffix parts after the first comma
    for p in parts[1:]:
        if p in SUFFIXES:
            suffix = p
        else:
            rest.append(p)

    if rest:
        # Last, First format
        last = parts[0]
        given = " ".join(rest).split()
    else:
        # First Middle Last format
        tokens = parts[0].split()

        # extract trailing suffix if present
        if len(tokens) > 1 and tokens[-1] in SUFFIXES:
            suffix = tokens.pop()

        # extend the last name backwards over particles (e.g. "VAN GRAAFEILAND" -> "VANGRAAFEILAND")
        i = len(tokens) - 1
        while i > 0 and tokens[i - 1] in LAST_NAME_PARTICLES:
            i -= 1
        last = "".join(tokens[i:])

        # any remaining words before the last name are given names or initials
        given = tokens[:i]

    parsed.update({
        "first": given[0] if given else "",
        "middle": " ".join(given[1:]),  # remaining names besides first name
        "suffix": suffix,
        "last": normalize_last_name(last),
    })
    return parsed
