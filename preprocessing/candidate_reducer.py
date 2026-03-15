"""
preprocessing/candidate_reducer.py — candidate pool reduction stage.

Sits between period buckets and panel generation:
  raw sources → filtered → period bucket → candidate pool → generated panel

The main workflow uses ``strategy: all`` (pass-through). Additional strategies
(``top_n``, ``manual_list``) are available as optional features when finer
control over panel composition is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class CandidateConfig:
    """Candidate reduction configuration (loaded from config.yaml)."""
    strategy: str                      # all | top_n | manual_list (optional)
    top_n: int | None = None           # used by top_n strategy
    allowlist_file: str | None = None  # used by manual_list strategy (optional)


def build_candidate_pool(
    period_df: pd.DataFrame,
    config: CandidateConfig,
    output_path: Path | None = None,
) -> pd.DataFrame:
    """
    Reduce *period_df* to a candidate pool for panel generation.

    Strategies
    ----------
    ``all`` (default):
        Pass all rows through unchanged. The stage is still explicit and
        logged for reproducibility.

    ``top_n`` (optional):
        Keep the first N rows by row order. Intended for future use with
        a scoring or ranked metadata column; for now selection is
        positional unless a ``score`` column is present.

    ``manual_list`` (optional feature):
        Keep only rows whose ``name`` appears in the allowlist file
        (one name per line, plain text). Useful for researcher-curated panels.

    Parameters
    ----------
    period_df:
        DataFrame representing one period bucket.
    config:
        Candidate reduction settings.
    output_path:
        If provided, write the resulting pool as a CSV to this path.

    Returns
    -------
    pd.DataFrame
        The candidate pool DataFrame.
    """
    strategy = config.strategy

    if strategy == "all":
        pool = period_df.copy()
        print(f"[candidate_reducer] strategy=all -> {len(pool)} candidates")

    elif strategy == "top_n":
        if config.top_n is None:
            raise ValueError("CandidateConfig: top_n must be set for strategy='top_n'")
        if "score" in period_df.columns:
            pool = period_df.nlargest(config.top_n, "score").reset_index(drop=True)
        else:
            pool = period_df.head(config.top_n).reset_index(drop=True)
        print(f"[candidate_reducer] strategy=top_n({config.top_n}) -> {len(pool)} candidates")

    elif strategy == "manual_list":
        # Optional feature: enabled only when allowlist_file is configured.
        if not config.allowlist_file:
            raise ValueError(
                "CandidateConfig: allowlist_file must be set for strategy='manual_list'. "
                "This is an optional feature — switch to strategy='all' for the default workflow."
            )
        allow_path = Path(config.allowlist_file)
        if not allow_path.exists():
            raise FileNotFoundError(f"Allowlist file not found: {allow_path}")
        allowed_names = set(
            line.strip()
            for line in allow_path.read_text().splitlines()
            if line.strip()
        )
        pool = period_df[period_df["name"].isin(allowed_names)].reset_index(drop=True)
        n_missing = len(allowed_names) - len(pool)
        if n_missing > 0:
            print(
                f"[candidate_reducer] WARNING: {n_missing} name(s) in allowlist "
                "were not found in the period bucket."
            )
        print(
            f"[candidate_reducer] strategy=manual_list -> {len(pool)} candidates "
            f"(from {len(allowed_names)} allowlist entries)"
        )

    else:
        raise ValueError(
            f"Unknown candidate reduction strategy: '{strategy}'. "
            "Supported: all | top_n | manual_list"
        )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pool.to_csv(output_path, index=False)
        print(f"[candidate_reducer] Pool written to {output_path}")

    return pool
