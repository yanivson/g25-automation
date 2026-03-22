"""
preprocessing/sample_metadata.py — authoritative per-sample metadata annotation.

Adds canonical metadata columns to any G25 DataFrame using the config's
prefix_to_region and region_to_macro lookup tables.  All downstream stages
(seeding, filtering, aggregation, reporting) must use these columns rather than
running their own ad-hoc substring matches on raw sample names.

Columns added
-------------
prefix                   — first underscore-delimited token of the sample name
canonical_region         — from prefix_to_region (falls back to prefix itself)
canonical_macro_region   — from region_to_macro (falls back to canonical_region)
broad_super_region       — continent-level grouping derived from macro_region
is_outlier_adjusted      — True when name matches pattern _o[A-Z]
allowed_in_standard_mode — True when not outlier_adjusted

The ``broad_super_region`` mapping is hardcoded here because super-regions are a
small, stable set of continental categories that do not need user configuration.
"""

from __future__ import annotations

import re

import pandas as pd


# ---------------------------------------------------------------------------
# Outlier pattern
# ---------------------------------------------------------------------------

_OUTLIER_PATTERN = re.compile(r"_o[A-Z]|_o[0-9]|_o$|_o\.")


# ---------------------------------------------------------------------------
# Continent-level super-region lookup
# Maps canonical_macro_region → broad_super_region
# ---------------------------------------------------------------------------

_MACRO_TO_SUPER: dict[str, str] = {
    # Europe
    "Northwestern Europe":  "Europe",
    "Western Europe":       "Europe",
    "Central Europe":       "Europe",
    "Southern Europe":      "Europe",
    "Southeastern Europe":  "Europe",
    "Northeastern Europe":  "Europe",
    # Near / Middle East
    "Eastern Mediterranean": "Middle East",
    "Middle East":           "Middle East",
    "Near East":             "Middle East",
    # North Africa
    "North Africa":          "North Africa",
    # Caucasus (treated as its own super-region)
    "Caucasus":              "Caucasus",
    # Central / Inner Asia
    "Central Asia":          "Central Asia",
    # East Asia
    "East Asia":             "East Asia",
    # South Asia
    "South Asia":            "South Asia",
    # Sub-Saharan Africa
    "Sub-Saharan Africa":    "Sub-Saharan Africa",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def annotate_df(
    df: pd.DataFrame,
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
) -> pd.DataFrame:
    """
    Return *df* with authoritative metadata columns appended.

    Parameters
    ----------
    df:
        Any G25 DataFrame with a ``name`` column.
    prefix_to_region:
        From config.yaml ``interpretation.prefix_to_region``.
    region_to_macro:
        From config.yaml ``interpretation.region_to_macro``.

    Returns
    -------
    pd.DataFrame
        Original df with extra columns:
        prefix, canonical_region, canonical_macro_region,
        broad_super_region, is_outlier_adjusted, allowed_in_standard_mode.
        All original columns are preserved and unchanged.
    """
    if "name" not in df.columns:
        raise ValueError("DataFrame must have a 'name' column.")

    out = df.copy()
    names: pd.Series = out["name"]

    out["prefix"] = names.apply(lambda n: n.split("_")[0])
    out["canonical_region"] = out["prefix"].apply(
        lambda p: prefix_to_region.get(p, p)
    )
    out["canonical_macro_region"] = out["canonical_region"].apply(
        lambda r: region_to_macro.get(r, r)
    )
    out["broad_super_region"] = out["canonical_macro_region"].apply(
        lambda m: _MACRO_TO_SUPER.get(m, "Other")
    )
    out["is_outlier_adjusted"] = names.apply(
        lambda n: bool(_OUTLIER_PATTERN.search(n))
    )
    out["allowed_in_standard_mode"] = ~out["is_outlier_adjusted"]

    return out


def coverage_counts(
    annotated_df: pd.DataFrame,
) -> dict[str, dict[str, int]]:
    """
    Return per-super_region and per-macro_region sample counts.

    Parameters
    ----------
    annotated_df:
        DataFrame produced by ``annotate_df()``.

    Returns
    -------
    dict with two keys:
        "by_super_region"  — {super_region: count}
        "by_macro_region"  — {macro_region: count}
    Only standard-mode (allowed_in_standard_mode) rows are counted.
    """
    std = annotated_df[annotated_df["allowed_in_standard_mode"].astype(bool)]
    return {
        "by_super_region": std["broad_super_region"].value_counts().to_dict(),
        "by_macro_region": std["canonical_macro_region"].value_counts().to_dict(),
    }
