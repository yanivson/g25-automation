"""
preprocessing/split_by_period.py — split source rows into period buckets.

Uses dates extracted by date_extractor.extract_dates(). Rows with unknown
dates and rows outside all defined periods are written to separate buckets
rather than dropped.

Outputs (when writing to disk):
  data/sources_periods/{period_name}.csv
  data/sources_periods/undated.csv
  data/sources_periods/out_of_range.csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def split_by_period(
    df: pd.DataFrame,
    dates: pd.Series,
    periods: dict[str, tuple[int, int]],
    output_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Assign each row of *df* to a period bucket based on the corresponding
    year in *dates*.

    Assignment rules:
      - Rows with ``None`` date → ``"undated"`` bucket
      - Rows whose year falls within a period's [start, end) range → that period
      - Rows with a year that matches no period → ``"out_of_range"`` bucket
      - Periods are non-overlapping by convention; if a year matches multiple
        periods the first match wins.

    Parameters
    ----------
    df:
        Source DataFrame.
    dates:
        Series of int | None aligned with df's index, from extract_dates().
    periods:
        Mapping of period name → (start_year_inclusive, end_year_exclusive).
        Example: ``{"classical": (-500, 200), "late_antiquity": (200, 800)}``
    output_dir:
        If provided, write each bucket as a CSV file to this directory.

    Returns
    -------
    dict[str, pd.DataFrame]
        Bucket name → DataFrame. Always contains ``"undated"`` and
        ``"out_of_range"`` keys even if empty.
    """
    buckets: dict[str, list[int]] = {name: [] for name in periods}
    buckets["undated"] = []
    buckets["out_of_range"] = []

    for idx, year in dates.items():
        if year is None:
            buckets["undated"].append(idx)
            continue

        matched = False
        for period_name, (start, end) in periods.items():
            if start <= year < end:
                buckets[period_name].append(idx)
                matched = True
                break

        if not matched:
            buckets["out_of_range"].append(idx)

    result: dict[str, pd.DataFrame] = {}
    for bucket_name, indices in buckets.items():
        subset = df.loc[indices].reset_index(drop=True)
        result[bucket_name] = subset

        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = output_dir / f"{bucket_name}.csv"
            subset.to_csv(out_path, index=False)
            print(
                f"[split_by_period] {bucket_name}: {len(subset)} rows -> {out_path}"
            )

    return result
