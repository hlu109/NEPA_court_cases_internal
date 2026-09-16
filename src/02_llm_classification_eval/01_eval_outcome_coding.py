"""
Evaluate LLM outcome coding performance on validation/test sets.
"""

from typing import Any
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix, ConfusionMatrixDisplay
import matplotlib.pyplot as plt
import sys
from pathlib import Path

# Add project root to Python path to allow imports from src.utils
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config import (
    AG_VAL_ASSIGNMENTS_PATH,
    AG_TEST_ASSIGNMENTS_PATH,
    ADELGLICKS_CLEANED_PATH,
    COURTLISTENER_CLUSTER_CLEANED_PATH,
    LLM_OPINION_CLF_PATH,
    LLM_JUDGES_CLF_PATH,
    INTERMEDIATE_DATA_DIR,
    FTR_PREDICTIONS_DIR,
)

FTR_EVAL_DIR = INTERMEDIATE_DATA_DIR / "Feature Classification Eval"
AG_VAL_EVAL_PATH = FTR_EVAL_DIR / "AG_val_performance.csv"
CL_VAL_EVAL_PATH = FTR_EVAL_DIR / "CL_performance.csv"
TEST_EVAL_PATH = FTR_EVAL_DIR / "test_performance.csv"
AG_VAL_JUDGE_DIAGNOSTICS_PATH = FTR_EVAL_DIR / "AG_val_judge_diagnostics.csv"
AG_TEST_JUDGE_DIAGNOSTICS_PATH = FTR_EVAL_DIR / "AG_test_judge_diagnostics.csv"
AG_VAL_JUDGE_JACCARD_HIST_PATH = FTR_EVAL_DIR / "AG_val_judge_jaccard_hist.png"
AG_TEST_JUDGE_JACCARD_HIST_PATH = FTR_EVAL_DIR / "AG_test_judge_jaccard_hist.png"
CL_VAL_JUDGE_DIAGNOSTICS_PATH = FTR_EVAL_DIR / "CL_val_judge_diagnostics.csv"
CL_VAL_JUDGE_JACCARD_HIST_PATH = FTR_EVAL_DIR / "CL_val_judge_jaccard_hist.png"

if not FTR_EVAL_DIR.exists():
    FTR_EVAL_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Metrics for case outcomes
# --------------------------------------------------------------------------


def compute_outcome_performance(y_true: pd.Series, y_pred: pd.Series) -> dict:
    """
    Compute accuracy and macro-averaged precision/recall/F1.
    """
    df = pd.DataFrame({"y_true": y_true, "y_pred": y_pred}).dropna()

    accuracy = accuracy_score(df["y_true"], df["y_pred"])
    macro_precision, macro_recall, macro_f1, _ = precision_recall_fscore_support(
        df["y_true"], df["y_pred"], average="macro", zero_division=0)
    micro_precision, micro_recall, micro_f1, _ = precision_recall_fscore_support(
        df["y_true"], df["y_pred"], average="micro", zero_division=0)
    return {
        "n": len(df),
        "accuracy": accuracy,
        "macro_precision": float(macro_precision),
        "macro_recall": float(macro_recall),
        "macro_f1": float(macro_f1),
        "micro_precision": float(micro_precision),
        "micro_recall": float(micro_recall),
        "micro_f1": float(micro_f1),
    }


def plot_outcome_confusion_matrix(
    y_true: pd.Series,
    y_pred: pd.Series,
    title: str,
    output_path: str | None = None,
):
    """
    Create and optionally save a confusion matrix figure. For case outcomes. 
    """
    df = pd.DataFrame({"y_true": y_true, "y_pred": y_pred}).dropna()
    if df.empty:
        return None

    labels = pd.unique(pd.concat([df["y_true"], pd.Series(["mixed", "UNK"])]))
    cm = confusion_matrix(df["y_true"], df["y_pred"], labels=labels)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=labels)
    fig, ax = plt.subplots(figsize=(6, 6))
    disp.plot(ax=ax, cmap="Blues", colorbar=False, values_format="d")
    ax.set_title(title)
    fig.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=300)
        print(f"Saved confusion matrix to: {output_path}")
    return fig


# --------------------------------------------------------------------------
# Metrics for judge classification
# --------------------------------------------------------------------------


def _judge_set_from_columns(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """
    Convert judge-name columns into a per-row set of non-empty names.

    Args:
        df: DataFrame containing judge-name columns.
        cols: Column names to include in the set.

    Returns:
        Series of Python sets (one set of judge names per row).
    """

    def _row_to_set(row):
        judges = set[Any]()
        for col in cols:
            value = row[col]
            if pd.notna(value) and value != "":
                judges.add(value)
        return judges

    return df[cols].apply(_row_to_set, axis=1)


def _jaccard_similarity(set_true: set[str], set_pred: set[str]) -> float:
    """
    Compute Jaccard similarity (intersection over union) between two judge-name sets.

    Args:
        set_true: Ground-truth judge set.
        set_pred: Predicted judge set.

    Returns:
        Jaccard/IOU score, or NaN if both sets are empty.
    """
    union = set_true | set_pred
    if not union:
        return np.nan
    return len(set_true & set_pred) / len(union)


def compute_judge_iou_metrics(eval_df: pd.DataFrame) -> dict:
    """
    Compute aggregate judge-panel IoU metrics for one split.

    Args:
        eval_df: Split-level dataframe containing true/pred judge columns.

    Returns:
        Metrics dictionary with mean/median Jaccard and exact set-match rate.
    """
    judge_true_cols = [
        "panel_judge_1_true", "panel_judge_2_true", "panel_judge_3_true"
    ]
    judge_pred_cols = [
        "panel_judge_1_pred", "panel_judge_2_pred", "panel_judge_3_pred"
    ]

    pair_df = eval_df[judge_true_cols + judge_pred_cols].copy()
    true_sets = _judge_set_from_columns(pair_df, judge_true_cols)
    pred_sets = _judge_set_from_columns(pair_df, judge_pred_cols)
    judge_eval_df = pd.DataFrame({
        "true_set": true_sets,
        "pred_set": pred_sets
    })

    judge_eval_df["jaccard"] = judge_eval_df.apply(
        lambda r: _jaccard_similarity(r["true_set"], r["pred_set"]), axis=1)
    exact_matches = judge_eval_df.apply(
        lambda r: r["true_set"] == r["pred_set"], axis=1).mean()

    return {
        "n": int(judge_eval_df["jaccard"].notna().sum()),
        "mean_iou": float(judge_eval_df["jaccard"].mean()),
        "median_iou": float(judge_eval_df["jaccard"].median()),
        "exact_set_match_rate": float(exact_matches),
    }


def judge_diagnostics(merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build dataframe of judge diagnostics for each case/row. Compare matches of individual judge names. 
    """
    true_cols = [
        "panel_judge_1_true", "panel_judge_2_true", "panel_judge_3_true"
    ]
    pred_cols = [
        "panel_judge_1_pred", "panel_judge_2_pred", "panel_judge_3_pred"
    ]

    diagnostics_df = merged_df[[
        "cluster_id",
        "lead_opinion_id",
        *true_cols,
        *pred_cols,
    ]].copy()

    true_sets = _judge_set_from_columns(diagnostics_df, true_cols)
    pred_sets = _judge_set_from_columns(diagnostics_df, pred_cols)
    diagnostics_df["true_judge_set"] = true_sets.map(
        lambda s: "; ".join(sorted(s)))
    diagnostics_df["pred_judge_set"] = pred_sets.map(
        lambda s: "; ".join(sorted(s)))
    diagnostics_df["judge_jaccard_score"] = diagnostics_df.apply(
        lambda r: _jaccard_similarity(true_sets.loc[r.name], pred_sets.loc[
            r.name]),
        axis=1,
    )

    diagnostics_df["pred_name_1_matched"] = diagnostics_df.apply(
        lambda r: int(
            pd.notna(r["panel_judge_1_pred"]) and r["panel_judge_1_pred"] != ""
            and r["panel_judge_1_pred"] in true_sets.loc[r.name]),
        axis=1,
    )
    diagnostics_df["pred_name_2_matched"] = diagnostics_df.apply(
        lambda r: int(
            pd.notna(r["panel_judge_2_pred"]) and r["panel_judge_2_pred"] != ""
            and r["panel_judge_2_pred"] in true_sets.loc[r.name]),
        axis=1,
    )
    diagnostics_df["pred_name_3_matched"] = diagnostics_df.apply(
        lambda r: int(
            pd.notna(r["panel_judge_3_pred"]) and r["panel_judge_3_pred"] != ""
            and r["panel_judge_3_pred"] in true_sets.loc[r.name]),
        axis=1,
    )
    diagnostics_df["matched_pred_name_count"] = diagnostics_df.apply(
        lambda r: len(true_sets.loc[r.name] & pred_sets.loc[r.name]),
        axis=1,
    )
    return diagnostics_df


def plot_judge_jaccard_histogram(
    diagnostics_df: pd.DataFrame,
    output_path: Path,
    title: str,
):
    """
    Plot and save histogram of per-case judge Jaccard scores.
    """
    scores = diagnostics_df["judge_jaccard_score"].dropna()

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(scores, bins=20)
    ax.set_title(title)
    ax.set_xlabel("IoU Score")
    ax.set_ylabel("Number of Court Cases")
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    print(f"Saved judge Jaccard histogram to: {output_path}")
    return fig


def evaluate_courtlistener_judges() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Evaluate LLM judge predictions against existing CourtListener judge variables.
    """
    merged_df = pd.read_csv(
        COURTLISTENER_CLUSTER_CLEANED_PATH,
        dtype={
            "cluster_id": str,
            "lead_opinion_id": str
        },
    )
    pred_judges_df = pd.read_csv(LLM_JUDGES_CLF_PATH,
                                 dtype={"opinion_id": str})
    pred_judges_subset = pred_judges_df[[
        "opinion_id",
        "panel_judge_1",
        "panel_judge_2",
        "panel_judge_3",
        "per_curiam",
        "file_source_indicator",
    ]].rename(
        columns={
            "panel_judge_1": "panel_judge_1_pred",
            "panel_judge_2": "panel_judge_2_pred",
            "panel_judge_3": "panel_judge_3_pred",
            "per_curiam": "per_curiam_pred",
        })
    merged_df = merged_df.merge(
        pred_judges_subset,
        left_on="lead_opinion_id",
        right_on="opinion_id",
        how="left",
    )
    merged_df = merged_df.drop(columns=["opinion_id"])

    cl_true_cols = ["cl_judge_1", "cl_judge_2", "cl_judge_3"]
    pred_cols = [
        "panel_judge_1_pred", "panel_judge_2_pred", "panel_judge_3_pred"
    ]

    availability_mask = (
        merged_df[cl_true_cols].fillna("").ne("").any(axis=1)
        | merged_df["cl_per_curiam"].fillna(0).astype(int).eq(1))
    diagnostics_df = merged_df[availability_mask].copy()
    missing_pred_mask = diagnostics_df["panel_judge_1_pred"].isna(
    ) & diagnostics_df["panel_judge_2_pred"].isna(
    ) & diagnostics_df["panel_judge_3_pred"].isna()
    missing_predictions = int(missing_pred_mask.sum())
    diagnostics_df = diagnostics_df[~missing_pred_mask].copy()

    true_sets = _judge_set_from_columns(diagnostics_df, cl_true_cols)
    pred_sets = _judge_set_from_columns(diagnostics_df, pred_cols)
    diagnostics_df["true_judge_set"] = true_sets.map(
        lambda s: "; ".join(sorted(s)))
    diagnostics_df["pred_judge_set"] = pred_sets.map(
        lambda s: "; ".join(sorted(s)))
    diagnostics_df["judge_jaccard_score"] = diagnostics_df.apply(
        lambda r: _jaccard_similarity(true_sets.loc[r.name], pred_sets.loc[
            r.name]),
        axis=1,
    )

    diagnostics_df["pred_name_1_matched"] = diagnostics_df.apply(
        lambda r: int(
            pd.notna(r["panel_judge_1_pred"]) and r["panel_judge_1_pred"] != ""
            and r["panel_judge_1_pred"] in true_sets.loc[r.name]),
        axis=1,
    )
    diagnostics_df["pred_name_2_matched"] = diagnostics_df.apply(
        lambda r: int(
            pd.notna(r["panel_judge_2_pred"]) and r["panel_judge_2_pred"] != ""
            and r["panel_judge_2_pred"] in true_sets.loc[r.name]),
        axis=1,
    )
    diagnostics_df["pred_name_3_matched"] = diagnostics_df.apply(
        lambda r: int(
            pd.notna(r["panel_judge_3_pred"]) and r["panel_judge_3_pred"] != ""
            and r["panel_judge_3_pred"] in true_sets.loc[r.name]),
        axis=1,
    )
    diagnostics_df["matched_pred_name_count"] = diagnostics_df.apply(
        lambda r: len(true_sets.loc[r.name] & pred_sets.loc[r.name]),
        axis=1,
    )

    per_curiam_eval = diagnostics_df[["cl_per_curiam",
                                      "per_curiam_pred"]].dropna().copy()
    per_curiam_accuracy = float((per_curiam_eval["cl_per_curiam"].astype(
        int) == per_curiam_eval["per_curiam_pred"].astype(int)).mean())

    metrics_df = pd.DataFrame([{
        "target":
        "cl_judge_panel_set",
        "n":
        int(diagnostics_df["judge_jaccard_score"].notna().sum()),
        "mean_iou":
        float(diagnostics_df["judge_jaccard_score"].mean()),
        "median_iou":
        float(diagnostics_df["judge_jaccard_score"].median()),
        "exact_set_match_rate":
        float((true_sets == pred_sets).mean()),
        "cl_per_curiam_accuracy":
        per_curiam_accuracy,
        "missing_predictions":
        missing_predictions,
    }])

    return metrics_df, diagnostics_df


def evaluate_split(
    assignments_path: str,
    ground_truth_path: str,
    ground_truth_id_col: str,
    assignments_id_col: str,
    split_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Evaluate a split (val or test) and return a metrics dataframe.
    """
    assignments = pd.read_csv(assignments_path,
                              dtype={
                                  "cluster_id": str,
                                  assignments_id_col: str
                              })
    ground_truth_df = pd.read_csv(ground_truth_path,
                                  dtype={
                                      "cluster_id": str,
                                      ground_truth_id_col: str
                                  })
    cl_df = pd.read_csv(COURTLISTENER_CLUSTER_CLEANED_PATH,
                        dtype={
                            "cluster_id": str,
                            "lead_opinion_id": str
                        })
    pred_outcomes_df = pd.read_csv(LLM_OPINION_CLF_PATH,
                                   dtype={"opinion_id": str})
    pred_judges_df = pd.read_csv(LLM_JUDGES_CLF_PATH,
                                 dtype={"opinion_id": str})

    assert "lead_opinion_id" in cl_df.columns, "lead_opinion_id missing from CourtListener cluster metadata"
    assert "opinion_id" in pred_outcomes_df.columns, "opinion_id missing from LLM coded outcomes"
    assert ground_truth_id_col in ground_truth_df.columns, f"Missing ground truth id column: {ground_truth_id_col}"
    assert assignments_id_col in assignments.columns, f"Missing assignments id column: {assignments_id_col}"

    # Join CL to get lead opinion id
    merged = assignments.merge(
        cl_df[["cluster_id", "lead_opinion_id"]],
        on="cluster_id",
        how="left",
    )

    # Join ground truth
    ground_truth_subset = ground_truth_df[[
        ground_truth_id_col,
        "district_outcome",
        "disposition",
        "prevailing_party",
        "panel_judge_1",
        "panel_judge_2",
        "panel_judge_3",
    ]].rename(
        columns={
            "district_outcome": "district_outcome_true",
            "disposition": "disposition_true",
            "prevailing_party": "prevailing_party_true",
            "panel_judge_1": "panel_judge_1_true",
            "panel_judge_2": "panel_judge_2_true",
            "panel_judge_3": "panel_judge_3_true",
        })
    merged = merged.merge(
        ground_truth_subset,
        left_on=assignments_id_col,
        right_on=ground_truth_id_col,
        how="left",
    )

    # Join LLM predictions
    pred_outcomes_subset = pred_outcomes_df[[
        "opinion_id", "district_outcome", "disposition", "prevailing_party"
    ]].rename(
        columns={
            "district_outcome": "district_outcome_pred",
            "disposition": "disposition_pred",
            "prevailing_party": "prevailing_party_pred",
        })
    merged = merged.merge(
        pred_outcomes_subset,
        left_on="lead_opinion_id",
        right_on="opinion_id",
        how="left",
    )
    merged = merged.drop(columns=["opinion_id"
                                  ])  # duplicate of lead_opinion_id
    pred_judges_subset = pred_judges_df[[
        "opinion_id", "panel_judge_1", "panel_judge_2", "panel_judge_3"
    ]].rename(
        columns={
            "panel_judge_1": "panel_judge_1_pred",
            "panel_judge_2": "panel_judge_2_pred",
            "panel_judge_3": "panel_judge_3_pred",
        })
    merged = merged.merge(
        pred_judges_subset,
        left_on="lead_opinion_id",
        right_on="opinion_id",
        how="left",
    )
    merged = merged.drop(columns=["opinion_id"
                                  ])  # duplicate of lead_opinion_id

    # Exclude rows with missing outcome predictions from metrics
    missing_outcome_pred_mask = merged["district_outcome_pred"].isna(
    ) & merged["disposition_pred"].isna(
    ) & merged["prevailing_party_pred"].isna()
    missing_outcome_predictions = int(missing_outcome_pred_mask.sum())
    outcome_eval_df = merged[~missing_outcome_pred_mask].copy()

    # Exclude rows with missing judge predictions from judge metrics
    missing_judge_pred_mask = merged["panel_judge_1_pred"].isna() & merged[
        "panel_judge_2_pred"].isna() & merged["panel_judge_3_pred"].isna()
    missing_judge_predictions = int(missing_judge_pred_mask.sum())
    judge_eval_df = merged[~missing_judge_pred_mask].copy()

    # Compute metrics
    metrics = []
    # case outcomes
    for target in ["district_outcome", "disposition", "prevailing_party"]:
        target_metrics = compute_outcome_performance(
            outcome_eval_df[f"{target}_true"],
            outcome_eval_df[f"{target}_pred"],
        )
        target_metrics["split"] = split_name
        target_metrics["target"] = target
        target_metrics["missing_predictions"] = missing_outcome_predictions
        metrics.append(target_metrics)

    # judges
    judge_metrics = compute_judge_iou_metrics(judge_eval_df)
    judge_metrics["split"] = split_name
    judge_metrics["target"] = "judge_panel_set"
    judge_metrics["missing_predictions"] = missing_judge_predictions
    metrics.append(judge_metrics)
    print(judge_metrics)

    metrics_df = pd.DataFrame(metrics)
    judge_diagnostics_df = judge_diagnostics(merged)
    return metrics_df, merged, judge_diagnostics_df


def run_val_eval(assignments_path: str, ground_truth_path: str,
                 ground_truth_id_col: str, assignments_id_col: str,
                 confusion_matrix_path_prefix: str) -> pd.DataFrame:
    val_metrics, val_merged, val_judge_diagnostics = evaluate_split(
        assignments_path, ground_truth_path, ground_truth_id_col,
        assignments_id_col, "val")
    plot_outcome_confusion_matrix(
        val_merged["district_outcome_true"],
        val_merged["district_outcome_pred"],
        title="District Outcome",
        output_path=f"{confusion_matrix_path_prefix}_district_outcome.png")
    plot_outcome_confusion_matrix(
        val_merged["disposition_true"],
        val_merged["disposition_pred"],
        title="Disposition",
        output_path=f"{confusion_matrix_path_prefix}_disposition.png")
    plot_outcome_confusion_matrix(
        val_merged["prevailing_party_true"],
        val_merged["prevailing_party_pred"],
        title="Prevailing Party",
        output_path=f"{confusion_matrix_path_prefix}_prevailing_party.png")
    return val_metrics, val_merged, val_judge_diagnostics


def run_test_eval(
    assignments_path: str,
    ground_truth_path: str,
    ground_truth_id_col: str,
    assignments_id_col: str,
    confusion_matrix_path_prefix: str,
) -> pd.DataFrame:
    test_metrics, test_merged, test_judge_diagnostics = evaluate_split(
        assignments_path, ground_truth_path, ground_truth_id_col,
        assignments_id_col, "test")
    plot_outcome_confusion_matrix(
        test_merged["district_outcome_true"],
        test_merged["district_outcome_pred"],
        title="District Outcome",
        output_path=f"{confusion_matrix_path_prefix}_district_outcome.png")
    plot_outcome_confusion_matrix(
        test_merged["disposition_true"],
        test_merged["disposition_pred"],
        title="Disposition",
        output_path=f"{confusion_matrix_path_prefix}_disposition.png")
    plot_outcome_confusion_matrix(
        test_merged["prevailing_party_true"],
        test_merged["prevailing_party_pred"],
        title="Prevailing Party",
        output_path=f"{confusion_matrix_path_prefix}_prevailing_party.png")
    return test_metrics, test_merged, test_judge_diagnostics


def main():
    # AdelGlicks val
    val_metrics, val_merged, val_judge_diagnostics = run_val_eval(
        str(AG_VAL_ASSIGNMENTS_PATH), str(ADELGLICKS_CLEANED_PATH), "id_num",
        "adelglicks_id", str(FTR_EVAL_DIR / "AG_val_confusion_matrix"))

    # Save predictions and performance metrics
    FTR_EVAL_DIR.mkdir(parents=True, exist_ok=True)
    FTR_PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)

    val_metrics.to_csv(AG_VAL_EVAL_PATH, index=False)
    print(f"Saved validation performance to: {AG_VAL_EVAL_PATH}")

    val_pred_path = FTR_PREDICTIONS_DIR / "AG_val_predictions.csv"
    val_merged.to_csv(val_pred_path, index=False)
    print(f"Saved validation predictions to: {val_pred_path}")

    val_judge_diagnostics.to_csv(AG_VAL_JUDGE_DIAGNOSTICS_PATH, index=False)
    print(
        f"Saved validation judge diagnostics to: {AG_VAL_JUDGE_DIAGNOSTICS_PATH}"
    )
    plot_judge_jaccard_histogram(
        val_judge_diagnostics,
        AG_VAL_JUDGE_JACCARD_HIST_PATH,
        title="Judge IoU Scores (Validation Set)",
    )

    # Run eval for LLM-classified judges against CourtListener metadata
    cl_val_metrics, cl_val_diagnostics = evaluate_courtlistener_judges()
    cl_val_metrics.to_csv(CL_VAL_EVAL_PATH, index=False)
    print(f"Saved CourtListener performance to: {CL_VAL_EVAL_PATH}")
    cl_val_diagnostics.to_csv(CL_VAL_JUDGE_DIAGNOSTICS_PATH, index=False)
    print(
        f"Saved CourtListener judge diagnostics to: {CL_VAL_JUDGE_DIAGNOSTICS_PATH}"
    )
    plot_judge_jaccard_histogram(
        cl_val_diagnostics,
        CL_VAL_JUDGE_JACCARD_HIST_PATH,
        title="CourtListener Judge IoU Scores (All Cases)",
    )

    # --------------------------------------------------------------------------
    # # Only run test evaluation once at the very end
    # # AdelGlicks test
    # test_metrics, test_merged, test_judge_diagnostics = run_test_eval(
    #     str(AG_TEST_ASSIGNMENTS_PATH),
    #     str(ADELGLICKS_CLEANED_PATH),
    #     "id_num",
    #     "adelglicks_id",
    #     str(FTR_EVAL_DIR / "AG_test_confusion_matrix")
    # )

    # # Save predictions and performance metrics
    # test_metrics.to_csv(TEST_EVAL_PATH, index=False)
    # print(f"Saved test performance to: {TEST_EVAL_PATH}")

    # test_pred_path = FTR_PREDICTIONS_DIR / "AG_test_predictions.csv"
    # test_merged.to_csv(test_pred_path, index=False)
    # print(f"Saved test predictions to: {test_pred_path}")
    # test_judge_diagnostics.to_csv(AG_TEST_JUDGE_DIAGNOSTICS_PATH, index=False)
    # print(f"Saved test judge diagnostics to: {AG_TEST_JUDGE_DIAGNOSTICS_PATH}")
    # plot_judge_jaccard_histogram(
    #     test_judge_diagnostics,
    #     AG_TEST_JUDGE_JACCARD_HIST_PATH,
    #     title = "Judge IoU Scores (Test Set)",
    # )


if __name__ == "__main__":
    main()
