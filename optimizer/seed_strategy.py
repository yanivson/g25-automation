"""
optimizer/seed_strategy.py — stratified macro-region pool construction.

Builds an initial candidate pool by sampling the nearest populations from
each macro-region, ensuring coverage across ancestry space rather than
concentrating all seeds near the target in G25 PCA space.

Two strategies are available:

build_coverage_aware_pool  (preferred)
    Metadata-driven.  Groups samples by their canonical_macro_region (derived
    from config's prefix_to_region + region_to_macro mappings) and selects the
    nearest ``per_macro`` populations per group.  Requires no hardcoded keyword
    lists — coverage is automatically complete for every macro_region that has
    at least one sample in the pool.

build_stratified_macro_pool  (legacy fallback)
    Keyword-based.  Kept for backward compatibility when no config mappings are
    available.  Uses hardcoded name-substring rules.

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
# Legacy keyword groups (used by build_stratified_macro_pool only)
# ---------------------------------------------------------------------------

_MACRO_REGIONS: dict[str, tuple[list[str], int]] = {
    # Northwest Europe — Britain, Ireland, Low Countries
    "NW_Europe":      (["England", "Scotland", "Ireland", "Wales", "Britain",
                        "IsleOfMan", "Orkney", "Frisian", "Netherlands",
                        "Belgium", "ChannelIslands", "Gibraltar"], 8),
    # Scandinavia / Nordic
    "Scandinavia":    (["Sweden", "Norway", "Denmark", "Iceland",
                        "Faroe", "Faroes", "Finland"], 8),
    # Germanic / Central Europe
    "Germanic":       (["Germany", "Austria", "Switzerland", "Czech",
                        "Czechia", "Slovakia", "Hungary", "France",
                        "Luxembourg"], 8),
    # Southern Europe — Iberia + Italy + Greece
    "South_Europe":   (["Italy", "Greece", "Iberia", "Spain", "Sicily",
                        "Sardinia", "Portugal", "Ibiza", "CanaryIslands"], 8),
    # Balkans / Southeastern Europe
    "Balkans":        (["Croatia", "Serbia", "Bulgaria", "Romania",
                        "Albania", "Bosnia", "BosniaHerzegovina",
                        "Macedonia", "Slovenia", "Montenegro"], 8),
    # Eastern Europe
    "Eastern_Europe": (["Russia", "Ukraine", "Moldova", "Crimea"], 8),
    # Levant / Near East
    "Levant":         (["Israel", "Jordan", "Lebanon", "Syria", "Iraq",
                        "Canaan", "Phoeni", "Natuf", "PPNB",
                        "Ghassul", "Negev"], 8),
    # Anatolia
    "Anatolia":       (["Turkey", "Anatolia"], 8),
    # Iran / Caucasus
    "Iran_Caucasus":  (["Iran", "Georgia", "Armenia", "Azerbaijan"], 8),
    # North Africa
    "North_Africa":   (["Egypt", "Libya", "Tunisia", "Algeria",
                        "Morocco", "Sudan"], 6),
    # Steppe / Central Asia
    "Central_Asia":   (["Kazakhstan", "Kazakstan", "Kazakhstann",
                        "Kyrgyzstan", "Uzbekistan", "Tajikistan",
                        "Turkmenistan", "Mongolia"], 4),
}

# Baltic/NE European countries sampled independently (2 per country)
_BALTIC_NE_COUNTRIES: dict[str, list[str]] = {
    "Poland":    ["Poland"],
    "Lithuania": ["Lithua"],
    "Latvia":    ["Latvia"],
    "Estonia":   ["Estonia"],
}
_BALTIC_NE_PER_COUNTRY: int = 2

# Default samples per macro-region for coverage-aware strategy
_DEFAULT_PER_MACRO: int = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _match_keywords(df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    """Return rows whose 'name' prefix (first token) matches any keyword exactly,
    or whose full name contains any keyword (case-insensitive substring fallback).
    """
    prefixes = df["name"].apply(lambda nm: nm.split("_")[0])
    exact_mask = prefixes.apply(
        lambda p: any(k.lower() == p.lower() for k in keywords)
    )
    sub_mask = df["name"].apply(
        lambda nm: any(k.lower() in nm.lower() for k in keywords)
    )
    return df[exact_mask | sub_mask].reset_index(drop=True)


def _nearest_n(pool: pd.DataFrame, target_coords: np.ndarray, n: int) -> pd.DataFrame:
    """Return the n rows nearest to target_coords (euclidean_distance column stripped)."""
    if pool.empty:
        return pool
    ranked = rank_candidates_by_distance(target_coords, pool)
    n = min(n, len(ranked))
    return ranked.iloc[:n].drop(columns=["euclidean_distance"], errors="ignore").reset_index(drop=True)


def _prefix(name: str) -> str:
    return name.split("_")[0]


# ---------------------------------------------------------------------------
# Coverage-aware strategy  (metadata-driven, preferred)
# ---------------------------------------------------------------------------

def build_coverage_aware_pool(
    candidate_pool_df: pd.DataFrame,
    target_coords: np.ndarray,
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    per_macro: int = _DEFAULT_PER_MACRO,
) -> pd.DataFrame:
    """
    Build a coverage-aware seed pool driven by config metadata.

    For every canonical_macro_region that has at least one sample in
    ``candidate_pool_df`` AND appears in ``region_to_macro`` (i.e. is a
    known ancestry macro-region), select the ``per_macro`` samples nearest
    to the target.  Unmapped prefixes whose names pass through as their own
    ad-hoc macro-region label (e.g. "Peru", "Vanuatu") are excluded from
    seeding — they may still appear as fill candidates during iteration.

    No hardcoded keyword lists are used — coverage is automatically complete
    for whatever mapped regions exist in the pool.

    Parameters
    ----------
    candidate_pool_df:
        Full candidate pool (must have 'name' + dim_* columns).
    target_coords:
        Target G25 coordinates, shape (25,).
    prefix_to_region:
        Mapping of name-prefix → canonical_region (from config.yaml).
    region_to_macro:
        Mapping of canonical_region → canonical_macro_region (from config.yaml).
    per_macro:
        Maximum samples to select per macro-region group.

    Returns
    -------
    pd.DataFrame
        Deduplicated seed pool covering all represented mapped macro-regions.
        Falls back to the full candidate_pool_df if the pool cannot be
        annotated (missing 'name' column or empty).
    """
    if candidate_pool_df.empty or "name" not in candidate_pool_df.columns:
        return candidate_pool_df

    # The set of valid macro-regions is the value-set of region_to_macro.
    # Any macro label NOT in this set is an unmapped pass-through (e.g. "Peru")
    # and must not receive dedicated seed slots.
    known_macros: set[str] = set(region_to_macro.values())

    pool = candidate_pool_df.copy()
    pool["_prefix"] = pool["name"].apply(_prefix)
    pool["_region"] = pool["_prefix"].apply(lambda p: prefix_to_region.get(p, p))
    pool["_macro"] = pool["_region"].apply(lambda r: region_to_macro.get(r, r))

    # Restrict seeding to known macro-regions only
    pool_known = pool[pool["_macro"].isin(known_macros)]

    frames: list[pd.DataFrame] = []
    seen: set[str] = set()

    macro_groups = pool_known["_macro"].unique()
    n_groups = len(macro_groups)
    print(
        f"[seed_strategy] coverage_aware: {n_groups} known macro-region groups, "
        f"{per_macro} each -> up to {n_groups * per_macro} seeds"
    )

    for macro in sorted(macro_groups):
        sub = pool_known[pool_known["_macro"] == macro].copy()
        sub = sub[~sub["name"].isin(seen)]
        sub_clean = sub.drop(columns=["_prefix", "_region", "_macro"], errors="ignore")
        selected = _nearest_n(sub_clean, target_coords, per_macro)
        if not selected.empty:
            frames.append(selected)
            seen.update(selected["name"].tolist())
            print(f"  [{macro}] {len(selected)} selected")
        else:
            print(f"  [{macro}] 0 selected (group empty after dedup)")

    unmapped_count = len(pool) - len(pool_known)
    if unmapped_count:
        print(
            f"[seed_strategy] {unmapped_count} samples from unmapped prefixes "
            f"excluded from seeding (still available as fill candidates)."
        )

    if not frames:
        print("[seed_strategy] WARNING: coverage_aware produced empty pool; falling back to full pool.")
        return candidate_pool_df

    result = pd.concat(frames, ignore_index=True)
    print(f"[seed_strategy] coverage_aware total seeds: {len(result)}")
    return result


# ---------------------------------------------------------------------------
# Legacy keyword-based strategy  (backward compatibility)
# ---------------------------------------------------------------------------

def build_stratified_macro_pool(
    candidate_pool_df: pd.DataFrame,
    target_coords: np.ndarray,
) -> pd.DataFrame:
    """
    Build a stratified pool by sampling the nearest n populations per
    macro-region using hardcoded keyword lists.

    This is the legacy fallback used when no config mappings are available.
    Prefer ``build_coverage_aware_pool`` when config is accessible.

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
