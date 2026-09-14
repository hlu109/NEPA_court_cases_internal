import pandas as pd
from pydantic import BaseModel, Field
from typing import List, Literal


class Case(BaseModel):
    disposition: Literal["affirm", "reverse", "mixed",
                         "UNK"] = Field(description="Case disposition")
    district_outcome: Literal[
        "plaintiff", "defendant", "mixed",
        "UNK"] = Field(description="Outcome from lower district court case")
    panel_judges: List[str] = Field(
        description=
        "List of all appellate judge names on the panel, in panel order.")
    opinion_authors: List[str] = Field(
        description=
        "List of judge name(s) who authored this specific opinion (majority, concurrence, or dissent)."
    )

    def save_json(self, file_path: str):
        """Save the case information to a JSON file."""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=4))


def _serialize_judges(judges: List[str]) -> str:
    if not judges:
        return ""
    return "; ".join(judge for judge in judges if judge)


def case_to_dataframe(case: Case) -> pd.DataFrame:
    """Convert a Case object to a DataFrame."""
    data = {
        "disposition": case.disposition,
        "district_outcome": case.district_outcome,
        "panel_judges": _serialize_judges(case.panel_judges),
        "panel_judge_count": len(case.panel_judges),
        "opinion_authors": _serialize_judges(case.opinion_authors),
        "opinion_author_count": len(case.opinion_authors),
    }
    df = pd.DataFrame([data])
    return df


def cases_to_dataframe(cases: List[Case]) -> pd.DataFrame:
    """Convert a list of Case objects to a DataFrame."""
    return pd.concat([case_to_dataframe(case) for case in cases],
                     ignore_index=True)
