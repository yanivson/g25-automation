"""
preprocessing/normalize_names.py — population name normalisation.

The original ``name`` column is never modified. A ``name_normalized`` helper
column is added and used downstream for matching and filtering logic.
"""

from __future__ import annotations

import re

import pandas as pd


def add_normalized_name(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a ``name_normalized`` column to *df* alongside the original ``name``.

    Normalisation rules applied to produce ``name_normalized``:
      - Strip leading/trailing whitespace
      - Collapse multiple internal spaces/tabs into a single space
      - Replace underscores with spaces

    The original ``name`` column is left completely unchanged.
    Casing is preserved in ``name_normalized``. A separate ``name_lower``
    column is NOT added unless a future matching requirement explicitly
    requires case-insensitive comparison.

    Parameters
    ----------
    df:
        DataFrame that must contain a ``name`` column.

    Returns
    -------
    pd.DataFrame
        The same DataFrame with ``name_normalized`` inserted directly after
        ``name``.
    """
    if "name" not in df.columns:
        raise ValueError("DataFrame must have a 'name' column.")

    normalized = (
        df["name"]
        .str.strip()
        .str.replace("_", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
    )

    # Insert name_normalized immediately after name for readability
    name_idx = df.columns.get_loc("name")
    df = df.copy()
    df.insert(name_idx + 1, "name_normalized", normalized)

    return df
