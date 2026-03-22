"""
preprocessing/outlier_filter.py — exclude outlier-adjusted samples from standard mode.

Samples in ancient DNA datasets are sometimes modelled as "outlier-corrected"
toward a named source population.  Example names:

    England_Saxon_oIran.SG          -> named outlier  (_o + UppercaseLetter)
    Croatia_Scitarjevo_Roman_oNorthEurope.SG
    Faroes_EarlyModern_o1.SG        -> indexed variant (_o + digit)
    Turkey_EarlyByzantine_1_o       -> bare trailing   (_o at end)
    Scotland_Viking_o.SG            -> bare before ext (_o + dot)
    Israel_MLBA_o                   -> bare trailing

The naming convention uses lower-case ``_o`` as the outlier marker, always
immediately following an underscore.  The original ``_o[A-Z]`` pattern only
caught named outliers; this module now handles all four forms.

In standard ancestry mode all such samples must be excluded because:
* Their G25 coordinates are deliberately shifted toward the outlier source.
* They are not representative of their labelled base population.
* When used as proxies they inject spurious ancestry signals.

Patterns NOT matched (intentional):
* ``_Ottoman``, ``_Ovilava``  — legitimate names starting with capital O after
  underscore; the marker is lower-case ``o``, not the start of a capitalised word.
"""

from __future__ import annotations

import re

import pandas as pd


# ---------------------------------------------------------------------------
# Outlier detection pattern
#
# Matches (case-sensitive lowercase o):
#   _o[A-Z]   named outlier suffix, e.g. _oIran, _oNorthEurope
#   _o[0-9]   indexed outlier variant, e.g. _o1, _o2, _o3
#   _o$       bare trailing _o at end of name, e.g. Turkey_EarlyByzantine_1_o
#   _o\.      bare _o immediately before extension, e.g. Scotland_Viking_o.SG
# ---------------------------------------------------------------------------

_OUTLIER_PATTERN = re.compile(r"_o[A-Z]|_o[0-9]|_o$|_o\.")


def is_outlier_adjusted(name: str) -> bool:
    """Return True if the sample name carries any recognised outlier-correction suffix."""
    return bool(_OUTLIER_PATTERN.search(name))


def filter_outliers(
    df: pd.DataFrame,
    *,
    enabled: bool = True,
    label: str = "",
) -> pd.DataFrame:
    """
    Remove outlier-adjusted samples from a G25 population DataFrame.

    Parameters
    ----------
    df:
        Must contain a ``name`` column.
    enabled:
        When False the DataFrame is returned unchanged (specialist / research mode).
    label:
        Optional string appended to the log line for context (e.g. "pool").

    Returns
    -------
    DataFrame
        Input without outlier-adjusted rows, index reset.
    """
    if not enabled or "name" not in df.columns:
        return df

    mask = ~df["name"].apply(is_outlier_adjusted)
    n_removed = int((~mask).sum())
    if n_removed:
        tag = f" [{label}]" if label else ""
        print(
            f"[outlier_filter]{tag} {n_removed} outlier-adjusted samples excluded "
            f"({len(df) - n_removed} kept)."
        )
    return df[mask].reset_index(drop=True)
