"""
preprocessing/date_extractor.py — configurable date extraction strategies.

Year values are integers (CE positive, BCE negative). Rows where a date
cannot be determined return None and are tagged as ``date_unknown`` by the
caller — they are never silently dropped.

Supported strategies (set in config.yaml):
  - regex_name          : extract year from population name string via regex
  - regex_name_extended : classify period from name tokens (EBA, Roman, Byzantine…)
  - column              : read year from a named column in the DataFrame
  - metadata_file       : look up year from an external CSV or JSON key→year map
  - unknown             : return None for all rows (when dates are not available)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pandas as pd


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class DateConfig:
    """Date extraction configuration (loaded from config.yaml)."""
    strategy: str                     # regex_name | regex_name_extended | column | metadata_file | unknown
    regex_pattern: str | None = None  # used by RegexNameStrategy
    column_name: str | None = None    # used by ColumnStrategy
    metadata_file: str | None = None  # used by MetadataFileStrategy


# ---------------------------------------------------------------------------
# Strategy protocol
# ---------------------------------------------------------------------------

class DateExtractionStrategy(Protocol):
    def extract_series(self, df: pd.DataFrame) -> pd.Series:
        """Return a Series of int | None aligned with df's index."""
        ...


# ---------------------------------------------------------------------------
# Concrete strategies
# ---------------------------------------------------------------------------

class RegexNameStrategy:
    """
    Extract year from the ``name`` column using a configurable regex.

    The pattern must contain at least one named or unnamed capture group:
      - If the name contains a BCE marker, the year is negated.
      - Example patterns:
          ``"(\\d+)BCE"``  → extracts 500 from "Pop_500BCE" → returns -500
          ``"(\\d+)CE"``   → extracts 300 from "Pop_300CE"  → returns  300
          ``"_(\\d+)$"``   → extracts bare number from tail of name

    If neither pattern matches, returns None for that row.
    """

    def __init__(self, pattern: str) -> None:
        self._bce = re.compile(r"(\d+)\s*BCE", re.IGNORECASE)
        self._ce = re.compile(r"(\d+)\s*CE", re.IGNORECASE)
        self._custom = re.compile(pattern) if pattern else None

    def extract_series(self, df: pd.DataFrame) -> pd.Series:
        results: list[int | None] = []
        for name in df["name"]:
            results.append(self._extract_one(str(name)))
        return pd.Series(results, index=df.index, dtype=object)

    def _extract_one(self, name: str) -> int | None:
        m = self._bce.search(name)
        if m:
            return -int(m.group(1))
        m = self._ce.search(name)
        if m:
            return int(m.group(1))
        if self._custom:
            m = self._custom.search(name)
            if m:
                try:
                    return int(m.group(1))
                except (IndexError, ValueError):
                    pass
        return None


class ColumnStrategy:
    """Read year from a named column in the DataFrame."""

    def __init__(self, column_name: str) -> None:
        self._col = column_name

    def extract_series(self, df: pd.DataFrame) -> pd.Series:
        if self._col not in df.columns:
            raise ValueError(
                f"DateExtractionStrategy(column): column '{self._col}' not found. "
                f"Available: {list(df.columns)}"
            )
        return pd.to_numeric(df[self._col], errors="coerce").astype(object).where(
            df[self._col].notna(), other=None
        )


class MetadataFileStrategy:
    """
    Look up year from an external key→year mapping.

    Supported file formats:
      - CSV with columns ``name`` and ``year``
      - JSON mapping ``{"population_name": year, ...}``

    Lookup is performed against the original ``name`` column (exact match).
    Missing entries return None.
    """

    def __init__(self, metadata_file: str | Path) -> None:
        path = Path(metadata_file)
        if not path.exists():
            raise FileNotFoundError(f"Metadata file not found: {path}")

        if path.suffix == ".json":
            self._mapping: dict[str, int | None] = json.loads(path.read_text())
        else:
            meta_df = pd.read_csv(path, dtype=str)
            if "name" not in meta_df.columns or "year" not in meta_df.columns:
                raise ValueError(
                    f"Metadata CSV must have 'name' and 'year' columns. Got: {list(meta_df.columns)}"
                )
            self._mapping = {
                row["name"]: int(row["year"]) if row["year"] not in ("", "nan") else None
                for _, row in meta_df.iterrows()
            }

    def extract_series(self, df: pd.DataFrame) -> pd.Series:
        results = [self._mapping.get(str(name)) for name in df["name"]]
        return pd.Series(results, index=df.index, dtype=object)


# ---------------------------------------------------------------------------
# Name-based period classifier (regex_name_extended strategy)
# ---------------------------------------------------------------------------

# Exact token matches (case-insensitive). Short abbreviations that must stand
# alone as a full underscore-delimited token to avoid false positives.
# Checked in listed order; first match wins.
_EXTENDED_EXACT_RULES: list[tuple[str, int]] = [
    ("MLBA", -1800),  # Middle-Late Bronze Age
    ("MBA",  -1800),  # Middle Bronze Age
    ("LBA",  -1800),  # Late Bronze Age
    ("EBA",  -1800),  # Early Bronze Age
    ("EIA",   -800),  # Early Iron Age
    ("LIA",   -800),  # Late Iron Age
    ("IA",    -800),  # Iron Age
]

# Substring matches within any token (case-insensitive). More specific entries
# appear before less specific ones to prevent partial shadowing (e.g. check
# "EarlyByzantine" before "Byzantine", "Hellenistic" before "Roman").
_EXTENDED_SUBSTRING_RULES: list[tuple[str, int]] = [
    # Late Antiquity (200–800)
    ("LATEANTIQUITY",      500),
    ("EARLYBYZANTINE",     500),
    ("WESTBYZANTINE",      500),
    ("ROMANBYZANTINE",     500),
    ("SOUTHEASTBYZANTINE", 500),
    ("BYZANTINE",          500),
    # Classical (–500–200)
    ("HELLENISTIC",          0),
    ("IMPERIAL",             0),
    ("REPUBLIC",             0),
    ("ROMAN",                0),
    # Medieval (800–1500)
    ("EMEDIEVAL",         1100),
    ("LMEDIEVAL",         1100),
    ("POSTMEDIEVAL",      1100),
    ("MEDIEVAL",          1100),
    ("VIKING",            1100),
    ("SAXON",             1100),
    # Bronze Age (–3300––1200)
    ("BRONZE",           -1800),
    # Iron Age (–1200––500)
    ("IRONAGE",           -800),
]


def _classify_name_extended(name: str) -> int | None:
    """
    Classify a population name into an approximate midpoint year via keyword
    matching on name tokens (split on ``_`` and ``.``).

    Two-pass approach:
      Pass 1 — exact token match for short abbreviations (IA, EBA, MBA, …)
      Pass 2 — substring match within tokens for longer keywords (Byzantine, Roman, …)

    Midpoint years returned:
      bronze_age     (–3300, –1200)  →  –1800
      iron_age       (–1200,  –500)  →   –800
      classical      (  –500,  200)  →      0
      late_antiquity (   200,  800)  →    500
      medieval       (   800, 1500)  →   1100

    Returns None when no pattern matches (row goes to "undated").
    """
    tokens = re.split(r"[_.\s]+", name)
    token_uppers = [t.upper() for t in tokens]

    # Pass 1: exact token matches (short abbreviations)
    for t_upper in token_uppers:
        for kw, year in _EXTENDED_EXACT_RULES:
            if t_upper == kw:
                return year

    # Pass 2: substring matches within tokens (longer period keywords)
    for t_upper in token_uppers:
        for kw, year in _EXTENDED_SUBSTRING_RULES:
            if kw in t_upper:
                return year

    return None


class RegexNameExtendedStrategy:
    """
    Classify populations into period buckets by matching name tokens against
    known period keywords.

    Returns an approximate midpoint year for the matched period so that the
    existing ``split_by_period`` logic works without modification.

    If no pattern matches, returns None (row goes to the "undated" bucket).
    """

    def extract_series(self, df: pd.DataFrame) -> pd.Series:
        results: list[int | None] = [
            _classify_name_extended(str(name)) for name in df["name"]
        ]
        return pd.Series(results, index=df.index, dtype=object)


class UnknownDateStrategy:
    """Return None for all rows. Used when date information is unavailable."""

    def extract_series(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series([None] * len(df), index=df.index, dtype=object)


# ---------------------------------------------------------------------------
# Factory + public entry point
# ---------------------------------------------------------------------------

def build_strategy(config: DateConfig) -> DateExtractionStrategy:
    """Instantiate the correct strategy from *config*."""
    if config.strategy == "regex_name":
        pattern = config.regex_pattern or ""
        return RegexNameStrategy(pattern)
    if config.strategy == "regex_name_extended":
        return RegexNameExtendedStrategy()
    if config.strategy == "column":
        if not config.column_name:
            raise ValueError("DateConfig: column_name must be set for strategy='column'")
        return ColumnStrategy(config.column_name)
    if config.strategy == "metadata_file":
        if not config.metadata_file:
            raise ValueError("DateConfig: metadata_file must be set for strategy='metadata_file'")
        return MetadataFileStrategy(config.metadata_file)
    if config.strategy == "unknown":
        return UnknownDateStrategy()
    raise ValueError(f"Unknown date extraction strategy: '{config.strategy}'")


def extract_dates(df: pd.DataFrame, config: DateConfig) -> pd.Series:
    """
    Apply the configured strategy to *df* and return a Series of int | None.

    Values are year CE (positive) or BCE (negative, stored as negative int).
    None means the date is unknown or could not be extracted.

    Parameters
    ----------
    df:
        Source DataFrame. Must have at least a ``name`` column.
    config:
        Date extraction configuration from config.yaml.

    Returns
    -------
    pd.Series
        Integer or None values, aligned with df's index.
    """
    strategy = build_strategy(config)
    return strategy.extract_series(df)
