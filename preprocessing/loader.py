"""
preprocessing/loader.py — delimiter-agnostic G25 file loader.

Supports both comma-delimited and tab-delimited G25 coordinate files.
Column layout: name (str), dim_1 … dim_25 (float) — 26 columns total.
Source files may or may not have a header row.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pandas as pd

_DIM_COLUMNS = [f"dim_{i}" for i in range(1, 26)]
_ALL_COLUMNS = ["name"] + _DIM_COLUMNS
_EXPECTED_COLS = 26


def load_g25_file(path: Path) -> pd.DataFrame:
    """
    Load a G25 coordinate file (target or source panel).

    Auto-detects delimiter: tries comma first, then tab. Picks whichever
    produces exactly 26 columns. If neither does, raises ``ValueError``.

    The returned DataFrame always has columns::

        ['name', 'dim_1', 'dim_2', ..., 'dim_25']

    The ``name`` column preserves the original string from the file (only
    leading/trailing whitespace is stripped). Dimension columns are floats.

    Parameters
    ----------
    path:
        Path to the G25 CSV or TSV file.

    Returns
    -------
    pd.DataFrame
        26-column DataFrame with standardised column names.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file cannot be parsed into exactly 26 columns with either
        comma or tab as the delimiter.
    """
    if not path.exists():
        raise FileNotFoundError(f"G25 file not found: {path}")

    raw = path.read_text(encoding="utf-8-sig", errors="replace")

    for delimiter in (",", "\t"):
        df = _try_load(raw, delimiter, path)
        if df is not None:
            return df

    raise ValueError(
        f"Cannot parse {path} as a G25 file. "
        f"Expected {_EXPECTED_COLS} columns with comma or tab delimiter. "
        "Check file format."
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_load(raw: str, delimiter: str, path: Path) -> pd.DataFrame | None:
    """
    Try to parse *raw* with the given *delimiter*.

    Returns a cleaned DataFrame if the column count matches, else None.
    """
    try:
        df = pd.read_csv(
            io.StringIO(raw),
            sep=delimiter,
            header=None,
            dtype=str,
            skip_blank_lines=True,
            on_bad_lines="skip",
        )
    except Exception:
        return None

    if df.shape[1] != _EXPECTED_COLS:
        return None

    # If the first row looks like a header (non-numeric first value that isn't
    # a valid population name followed by numbers), drop it.
    df = _drop_header_if_present(df)

    df.columns = _ALL_COLUMNS  # type: ignore[assignment]

    # Strip whitespace from name column only — never alter values
    df["name"] = df["name"].str.strip()

    # Cast dimension columns to float; rows that fail conversion are dropped
    # with a warning so raw data remains immutable.
    for col in _DIM_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    bad = df[_DIM_COLUMNS].isnull().any(axis=1)
    if bad.any():
        n = bad.sum()
        print(
            f"[loader] WARNING: {n} row(s) in {path.name} had non-numeric "
            "dimension values and were dropped."
        )
        df = df[~bad].reset_index(drop=True)

    return df


def _drop_header_if_present(df: pd.DataFrame) -> pd.DataFrame:
    """
    If the first row contains a non-numeric string in column 1 (the first
    dimension), treat it as a header row and drop it.
    """
    if df.empty:
        return df
    first_dim = str(df.iloc[0, 1]).strip()
    try:
        float(first_dim)
        return df  # first dim is numeric — no header
    except ValueError:
        return df.iloc[1:].reset_index(drop=True)
