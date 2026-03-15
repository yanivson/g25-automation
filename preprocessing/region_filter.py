"""
preprocessing/region_filter.py — config-driven, auditable region filter.

Every run writes two audit CSV files:
  - {run_id}_kept.csv    : rows that passed, with a ``match_reason`` column
  - {run_id}_removed.csv : rows that failed, with a ``removal_reason`` column

The audit files are written even if a set is empty, to ensure reproducibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class RegionConfig:
    """Region filter configuration (loaded from config.yaml)."""
    allowed_keywords: list[str]
    exclusion_keywords: list[str]


def filter_by_region(
    df: pd.DataFrame,
    config: RegionConfig,
    audit_dir: Path,
    run_id: str,
) -> pd.DataFrame:
    """
    Filter *df* to rows whose ``name_normalized`` contains at least one
    allowed keyword (case-insensitive), then remove any rows that also match
    an exclusion keyword.

    Audit files are written to *audit_dir* regardless of whether sets are empty.

    Parameters
    ----------
    df:
        Input DataFrame. Must have ``name_normalized`` column (call
        ``add_normalized_name`` first).
    config:
        Region filter settings.
    audit_dir:
        Directory where audit CSV files will be written.
    run_id:
        Identifier appended to audit filenames (e.g. a timestamp string).

    Returns
    -------
    pd.DataFrame
        Kept rows with an added ``match_reason`` column. Original column
        order and values are preserved.

    Raises
    ------
    ValueError
        If ``name_normalized`` column is missing.
    """
    if "name_normalized" not in df.columns:
        raise ValueError(
            "DataFrame must have 'name_normalized' column. "
            "Call add_normalized_name() first."
        )

    audit_dir.mkdir(parents=True, exist_ok=True)

    df = df.copy()
    df["match_reason"] = ""
    df["removal_reason"] = ""

    # Step 1 — allowed keyword pass
    for keyword in config.allowed_keywords:
        mask = df["name_normalized"].str.contains(keyword, case=False, regex=False)
        untagged = df["match_reason"] == ""
        df.loc[mask & untagged, "match_reason"] = f"keyword:{keyword}"

    allowed_mask = df["match_reason"] != ""
    df.loc[~allowed_mask, "removal_reason"] = "no_region_match"

    # Step 2 — exclusion keyword pass (applied only to currently-allowed rows)
    for keyword in config.exclusion_keywords:
        ex_mask = df["name_normalized"].str.contains(keyword, case=False, regex=False)
        already_kept = allowed_mask & ex_mask
        df.loc[already_kept, "removal_reason"] = f"exclusion:{keyword}"
        df.loc[already_kept, "match_reason"] = ""  # un-keep
        allowed_mask = df["match_reason"] != ""

    # Partition
    kept = df[df["match_reason"] != ""].drop(columns=["removal_reason"]).reset_index(drop=True)
    removed = df[df["match_reason"] == ""].drop(columns=["match_reason"]).reset_index(drop=True)

    # Write audit files
    kept_path = audit_dir / f"{run_id}_kept.csv"
    removed_path = audit_dir / f"{run_id}_removed.csv"
    kept.to_csv(kept_path, index=False)
    removed.to_csv(removed_path, index=False)
    print(
        f"[region_filter] kept={len(kept)}, removed={len(removed)} "
        f"-> audit written to {audit_dir}"
    )

    return kept
