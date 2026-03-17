"""
optimizer/seed_strategy.py — stratified macro-region pool construction.

Builds an initial candidate pool by sampling the nearest populations from
each macro-region, ensuring coverage across ancestry space rather than
concentrating all seeds near the target in G25 PCA space.

Strategy: stratified_macro
  For each of 5 continental macro-regions, select the 8 nearest populations
  to the target.  For each Baltic/NE European country (Poland, Lithuania,
  Latvia, Estonia), select the 2 nearest populations independently.
  Duplicate names are dropped (first occurrence wins).

The returned DataFrame is used as both the initial panel and the refill
candidate set for the optimizer run.  It is a strict subset of the input
candidate_pool_df.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from optimizer.preselection import rank_candidates_by_distance

_DIM_COLS = [f"dim_{i}" for i in range(1, 26)]

# ---------------------------------------------------------------------------
# Macro-region keyword groups and per-region sample counts
# ---------------------------------------------------------------------------

_MACRO_REGIONS: dict[str, tuple[list[str], int]] = {
    "Levant":        (["Israel", "Jordan", "Lebanon", "Syria", "Canaan",
                       "Phoeni", "Natuf", "PPNB", "Ghassul", "Negev"], 8),
    "South_Europe":  (["Italy", "Greece", "Iberia", "Spain", "Sicily",
                       "Sardinia", "Portugal"], 8),
    "Anatolia":      (["Turkey", "Anatolia"], 8),
    "Balkans":       (["Croatia", "Serbia", "Bulgaria", "Romania",
                       "Albania", "Bosnia", "Macedonia", "Slovenia"], 8),
    "Iran_Caucasus": (["Iran", "Georgia", "Armenia", "Azerbaijan"], 8),
}

# Baltic/NE European countries sampled independently (2 per country)
_BALTIC_NE_COUNTRIES: dict[str, list[str]] = {
    "Poland":    ["Poland"],
    "Lithuania": ["Lithua"],
    "Latvia":    ["Latvia"],
    "Estonia":   ["Estonia"],
}
_BALTIC_NE_PER_COUNTRY: int = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _match_keywords(df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    """Return rows whose 'name' contains any keyword (case-insensitive)."""
    mask = df["name"].apply(lambda nm: any(k.lower() in nm.lower() for k in keywords))
    return df[mask].reset_index(drop=True)


def _nearest_n(pool: pd.DataFrame, target_coords: np.ndarray, n: int) -> pd.DataFrame:
    """Return the n rows nearest to target_coords (euclidean_distance column stripped)."""
    if pool.empty:
        return pool
    ranked = rank_candidates_by_distance(target_coords, pool)
    n = min(n, len(ranked))
    return ranked.iloc[:n].drop(columns=["euclidean_distance"], errors="ignore").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_stratified_macro_pool(
    candidate_pool_df: pd.DataFrame,
    target_coords: np.ndarray,
) -> pd.DataFrame:
    """
    Build a stratified pool by sampling the nearest n populations per
    macro-region, plus the nearest _BALTIC_NE_PER_COUNTRY per Baltic/NE country.

    Population names that appear in multiple regions are included once
    (first match wins — macro-regions are sampled before Baltic/NE).

    Falls back to the full candidate_pool_df if all keyword matches are empty.

    Parameters
    ----------
    candidate_pool_df:
        Full candidate pool to sample from.
    target_coords:
        Target G25 coordinates, shape (25,).

    Returns
    -------
    pd.DataFrame
        Stratified sub-pool used as both the initial panel and candidate set.
    """
    frames: list[pd.DataFrame] = []
    seen: set[str] = set()

    for _region, (kws, n) in _MACRO_REGIONS.items():
        sub = _match_keywords(candidate_pool_df, kws)
        sub = sub[~sub["name"].isin(seen)]
        selected = _nearest_n(sub, target_coords, n)
        if not selected.empty:
            frames.append(selected)
            seen.update(selected["name"].tolist())

    for country_kws in _BALTIC_NE_COUNTRIES.values():
        sub = _match_keywords(candidate_pool_df, country_kws)
        sub = sub[~sub["name"].isin(seen)]
        selected = _nearest_n(sub, target_coords, _BALTIC_NE_PER_COUNTRY)
        if not selected.empty:
            frames.append(selected)
            seen.update(selected["name"].tolist())

    if not frames:
        return candidate_pool_df

    return pd.concat(frames, ignore_index=True)
