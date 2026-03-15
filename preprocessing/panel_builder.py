"""
preprocessing/panel_builder.py — convert a candidate pool DataFrame to G25 panel text.

The panel text format expected by the Vahaduo engine:
  PopulationName,dim1,dim2,...,dim25
  (one line per population, comma-separated, no header)

Uses the original ``name`` column — never the normalized variant.
"""

from __future__ import annotations

import pandas as pd

_DIM_COLUMNS = [f"dim_{i}" for i in range(1, 26)]


def build_panel(df: pd.DataFrame) -> str:
    """
    Convert a candidate pool DataFrame to a G25 panel text string.

    Parameters
    ----------
    df:
        Candidate pool DataFrame with ``name`` and ``dim_1``…``dim_25`` columns.

    Returns
    -------
    str
        Multi-line panel string. Each line is:
        ``PopulationName,dim1,dim2,...,dim25``
        Trailing newline is included.

    Raises
    ------
    ValueError
        If required columns are missing.
    """
    missing = [c for c in ["name"] + _DIM_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"panel_builder: missing columns: {missing}")

    lines: list[str] = []
    for _, row in df.iterrows():
        dims = ",".join(str(row[c]) for c in _DIM_COLUMNS)
        lines.append(f"{row['name']},{dims}")

    return "\n".join(lines) + "\n"
