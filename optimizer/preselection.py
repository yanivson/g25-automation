"""
optimizer/preselection.py — deterministic distance-based candidate preselection.

Ranks candidate populations by Euclidean distance to the target across all 25
G25 coordinate dimensions. Used for both initial panel seeding and refill
candidate ordering.

Distance formula: Euclidean — sqrt(sum((t_i - c_i)^2 for i in 1..25))
Tie-breaking:     equal distances broken by name (alphabetical, ascending)
Artifact:         preselection.csv written to the run directory at run start
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_DIM_COLUMNS = [f"dim_{i}" for i in range(1, 26)]


def parse_target_coords(target_text: str) -> np.ndarray:
    """
    Parse a single-row G25 target string into a (25,) coordinate array.

    Expected format: ``name,dim1,dim2,...,dim25`` (comma-separated, 26 fields).

    Parameters
    ----------
    target_text:
        Single-population G25 string, e.g. ``"Yaniv_scaled,0.095611,..."``.

    Returns
    -------
    np.ndarray, shape (25,)

    Raises
    ------
    ValueError
        If the string does not contain exactly 26 comma-separated fields.
    """
    parts = target_text.strip().split(",")
    if len(parts) != 26:
        raise ValueError(
            f"target_text must have 26 comma-separated fields (name + 25 dims). "
            f"Got {len(parts)}: {target_text[:80]!r}"
        )
    return np.array([float(x) for x in parts[1:]], dtype=float)


def rank_candidates_by_distance(
    target_coords: np.ndarray,
    candidate_pool_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Return a copy of *candidate_pool_df* with an added ``euclidean_distance``
    column, sorted by ``(euclidean_distance ASC, name ASC)``.

    The sort order is fully deterministic: equal distances are broken by the
    population name, matching the tie-breaking convention used elsewhere in
    the optimizer (exhausted_set refill ordering).

    Parameters
    ----------
    target_coords:
        Shape ``(25,)`` array of the target's G25 coordinate values.
    candidate_pool_df:
        Candidate pool DataFrame with ``name`` + ``dim_1``..``dim_25`` columns.

    Returns
    -------
    pd.DataFrame
        Same rows as input, with ``euclidean_distance`` column added and rows
        sorted nearest-first. Index is reset (0-based).
    """
    coords = candidate_pool_df[_DIM_COLUMNS].to_numpy(dtype=float)
    diffs = coords - target_coords          # (N, 25) broadcast
    distances = np.sqrt((diffs ** 2).sum(axis=1))   # (N,)

    df = candidate_pool_df.copy()
    df["euclidean_distance"] = distances
    df = df.sort_values(["euclidean_distance", "name"], ascending=[True, True])
    return df.reset_index(drop=True)
