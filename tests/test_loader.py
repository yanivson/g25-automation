"""tests/test_loader.py — unit tests for preprocessing/loader.py."""

from pathlib import Path

import pytest

from preprocessing.loader import load_g25_file, _ALL_COLUMNS

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_csv_column_count():
    """CSV fixture loads into exactly 26 columns."""
    df = load_g25_file(FIXTURES / "sample_target.csv")
    assert list(df.columns) == _ALL_COLUMNS
    assert df.shape[1] == 26


def test_load_tsv_column_count():
    """TSV fixture loads into exactly 26 columns."""
    df = load_g25_file(FIXTURES / "sample_target.tsv")
    assert list(df.columns) == _ALL_COLUMNS
    assert df.shape[1] == 26


def test_load_csv_name_preserved():
    """Name column contains the original population string."""
    df = load_g25_file(FIXTURES / "sample_target.csv")
    assert df["name"].iloc[0] == "Modern_Greek"


def test_load_tsv_name_preserved():
    """Name column contains the original population string (TSV)."""
    df = load_g25_file(FIXTURES / "sample_target.tsv")
    assert df["name"].iloc[0] == "Modern_Greek"


def test_load_csv_dimensions_are_float():
    """All dimension columns are float dtype."""
    df = load_g25_file(FIXTURES / "sample_target.csv")
    for col in [c for c in df.columns if c.startswith("dim_")]:
        assert df[col].dtype.kind == "f", f"{col} is not float"


def test_load_source_multi_row():
    """Multi-row source CSV loads all valid rows."""
    df = load_g25_file(FIXTURES / "sample_source.csv")
    assert len(df) == 6


def test_load_bad_column_count_raises():
    """Files with wrong column count raise ValueError with path info."""
    with pytest.raises(ValueError, match="sample_source_bad_cols"):
        load_g25_file(FIXTURES / "sample_source_bad_cols.csv")


def test_load_missing_file_raises():
    """Missing file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_g25_file(FIXTURES / "nonexistent.csv")
