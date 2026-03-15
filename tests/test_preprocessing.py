"""tests/test_preprocessing.py — unit tests for preprocessing modules."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from preprocessing.loader import load_g25_file
from preprocessing.normalize_names import add_normalized_name
from preprocessing.region_filter import RegionConfig, filter_by_region
from preprocessing.date_extractor import DateConfig, extract_dates
from preprocessing.split_by_period import split_by_period
from preprocessing.candidate_reducer import CandidateConfig, build_candidate_pool
from preprocessing.panel_builder import build_panel

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(names: list[str]) -> pd.DataFrame:
    """Build a minimal 26-column DataFrame with given names."""
    dims = {f"dim_{i}": [0.0] * len(names) for i in range(1, 26)}
    return pd.DataFrame({"name": names, **dims})


def _base_config() -> RegionConfig:
    return RegionConfig(
        allowed_keywords=["Anatolia", "Greece", "Levant", "North Africa", "Middle East", "Europe"],
        exclusion_keywords=[],
    )


# ---------------------------------------------------------------------------
# normalize_names
# ---------------------------------------------------------------------------

class TestNormalizeNames:
    def test_adds_column(self):
        df = _make_df(["Pop_A"])
        result = add_normalized_name(df)
        assert "name_normalized" in result.columns

    def test_original_name_unchanged(self):
        df = _make_df(["Pop_With_Underscores"])
        result = add_normalized_name(df)
        assert result["name"].iloc[0] == "Pop_With_Underscores"

    def test_underscores_replaced_with_spaces(self):
        df = _make_df(["Pop_With_Underscores"])
        result = add_normalized_name(df)
        assert result["name_normalized"].iloc[0] == "Pop With Underscores"

    def test_case_preserved(self):
        df = _make_df(["Modern_Greek"])
        result = add_normalized_name(df)
        assert result["name_normalized"].iloc[0] == "Modern Greek"

    def test_whitespace_collapsed(self):
        df = _make_df(["Pop  A"])  # double space
        result = add_normalized_name(df)
        assert result["name_normalized"].iloc[0] == "Pop A"

    def test_missing_name_column_raises(self):
        df = pd.DataFrame({"other": [1, 2]})
        with pytest.raises(ValueError, match="'name' column"):
            add_normalized_name(df)


# ---------------------------------------------------------------------------
# region_filter
# ---------------------------------------------------------------------------

class TestRegionFilter:
    def _run(self, names: list[str], tmp_path: Path) -> pd.DataFrame:
        df = add_normalized_name(_make_df(names))
        config = _base_config()
        return filter_by_region(df, config, tmp_path, "test_run")

    def test_keeps_allowed_keyword(self, tmp_path: Path):
        kept = self._run(["Anatolia_Neolithic"], tmp_path)
        assert len(kept) == 1
        assert kept["name"].iloc[0] == "Anatolia_Neolithic"

    def test_removes_non_matching(self, tmp_path: Path):
        kept = self._run(["East_Asian_Pop"], tmp_path)
        assert len(kept) == 0

    def test_mixed_keeps_and_removes(self, tmp_path: Path):
        kept = self._run(["Anatolia_Neolithic", "East_Asian_Pop", "Greece_Mycenaean"], tmp_path)
        assert len(kept) == 2

    def test_audit_files_written(self, tmp_path: Path):
        self._run(["Anatolia_Neolithic", "East_Asian_Pop"], tmp_path)
        assert (tmp_path / "test_run_kept.csv").exists()
        assert (tmp_path / "test_run_removed.csv").exists()

    def test_kept_has_match_reason(self, tmp_path: Path):
        kept = self._run(["Anatolia_Neolithic"], tmp_path)
        assert "match_reason" in kept.columns
        assert kept["match_reason"].iloc[0].startswith("keyword:")

    def test_removed_file_has_removal_reason(self, tmp_path: Path):
        self._run(["East_Asian_Pop"], tmp_path)
        removed = pd.read_csv(tmp_path / "test_run_removed.csv")
        assert "removal_reason" in removed.columns
        assert removed["removal_reason"].iloc[0] == "no_region_match"

    def test_exclusion_keyword(self, tmp_path: Path):
        df = add_normalized_name(_make_df(["Greece_Modern", "Anatolia_Neolithic"]))
        config = RegionConfig(
            allowed_keywords=["Greece", "Anatolia"],
            exclusion_keywords=["Modern"],
        )
        kept = filter_by_region(df, config, tmp_path, "excl_run")
        # Greece_Modern should be excluded; Anatolia_Neolithic should remain
        assert len(kept) == 1
        assert kept["name"].iloc[0] == "Anatolia_Neolithic"

    def test_empty_sets_still_write_audit(self, tmp_path: Path):
        # All removed
        self._run(["East_Asian"], tmp_path)
        assert (tmp_path / "test_run_kept.csv").exists()
        kept_df = pd.read_csv(tmp_path / "test_run_kept.csv")
        assert len(kept_df) == 0


# ---------------------------------------------------------------------------
# date_extractor
# ---------------------------------------------------------------------------

class TestDateExtractor:
    def test_regex_strategy_bce(self):
        df = _make_df(["Anatolia_7000BCE"])
        config = DateConfig(strategy="regex_name")
        dates = extract_dates(df, config)
        assert dates.iloc[0] == -7000

    def test_regex_strategy_ce(self):
        df = _make_df(["Rome_400CE"])
        config = DateConfig(strategy="regex_name")
        dates = extract_dates(df, config)
        assert dates.iloc[0] == 400

    def test_regex_strategy_no_match_returns_none(self):
        df = _make_df(["Modern_Greek"])
        config = DateConfig(strategy="regex_name")
        dates = extract_dates(df, config)
        assert dates.iloc[0] is None

    def test_unknown_strategy_returns_none(self):
        df = _make_df(["Anatolia_7000BCE", "Modern_Greek"])
        config = DateConfig(strategy="unknown")
        dates = extract_dates(df, config)
        assert all(v is None for v in dates)

    def test_column_strategy(self):
        df = _make_df(["Pop_A", "Pop_B"])
        df["date"] = [300, None]
        config = DateConfig(strategy="column", column_name="date")
        dates = extract_dates(df, config)
        assert dates.iloc[0] == 300
        assert dates.iloc[1] is None

    def test_unknown_strategy_raises_on_invalid(self):
        df = _make_df(["Pop"])
        config = DateConfig(strategy="invalid_strategy")
        with pytest.raises(ValueError, match="Unknown date extraction strategy"):
            extract_dates(df, config)


# ---------------------------------------------------------------------------
# split_by_period
# ---------------------------------------------------------------------------

class TestSplitByPeriod:
    _periods = {
        "classical": (-500, 200),
        "late_antiquity": (200, 800),
        "medieval": (800, 1500),
    }

    def test_classical_range(self):
        df = _make_df(["Pop_A"])
        dates = pd.Series([-100], index=df.index)
        result = split_by_period(df, dates, self._periods)
        assert len(result["classical"]) == 1

    def test_late_antiquity_range(self):
        df = _make_df(["Pop_A"])
        dates = pd.Series([500], index=df.index)
        result = split_by_period(df, dates, self._periods)
        assert len(result["late_antiquity"]) == 1

    def test_undated_bucket(self):
        df = _make_df(["Pop_A"])
        dates = pd.Series([None], index=df.index)
        result = split_by_period(df, dates, self._periods)
        assert len(result["undated"]) == 1

    def test_out_of_range(self):
        df = _make_df(["Pop_A"])
        dates = pd.Series([2000], index=df.index)
        result = split_by_period(df, dates, self._periods)
        assert len(result["out_of_range"]) == 1

    def test_all_buckets_present(self):
        df = _make_df(["A", "B"])
        dates = pd.Series([None, -100], index=df.index)
        result = split_by_period(df, dates, self._periods)
        assert "undated" in result
        assert "out_of_range" in result
        assert "classical" in result

    def test_writes_csv_files(self, tmp_path: Path):
        df = _make_df(["Pop_A"])
        dates = pd.Series([-100], index=df.index)
        split_by_period(df, dates, self._periods, output_dir=tmp_path)
        assert (tmp_path / "classical.csv").exists()


# ---------------------------------------------------------------------------
# candidate_reducer
# ---------------------------------------------------------------------------

class TestCandidateReducer:
    def test_all_strategy_passthrough(self):
        df = _make_df(["A", "B", "C"])
        config = CandidateConfig(strategy="all")
        pool = build_candidate_pool(df, config)
        assert len(pool) == 3

    def test_top_n_strategy(self):
        df = _make_df(["A", "B", "C", "D"])
        config = CandidateConfig(strategy="top_n", top_n=2)
        pool = build_candidate_pool(df, config)
        assert len(pool) == 2

    def test_manual_list_optional_requires_file(self):
        df = _make_df(["A"])
        config = CandidateConfig(strategy="manual_list", allowlist_file=None)
        with pytest.raises(ValueError, match="optional feature"):
            build_candidate_pool(df, config)

    def test_unknown_strategy_raises(self):
        df = _make_df(["A"])
        config = CandidateConfig(strategy="unknown_strategy")
        with pytest.raises(ValueError, match="Unknown candidate reduction strategy"):
            build_candidate_pool(df, config)


# ---------------------------------------------------------------------------
# panel_builder
# ---------------------------------------------------------------------------

class TestPanelBuilder:
    def test_output_format(self):
        df = load_g25_file(FIXTURES / "sample_target.csv")
        panel = build_panel(df)
        lines = [l for l in panel.strip().splitlines() if l]
        assert len(lines) == 1
        parts = lines[0].split(",")
        assert len(parts) == 26

    def test_uses_original_name(self):
        df = add_normalized_name(load_g25_file(FIXTURES / "sample_target.csv"))
        panel = build_panel(df)
        # Panel must use original name, not normalized
        assert "Modern_Greek" in panel

    def test_missing_columns_raises(self):
        df = pd.DataFrame({"name": ["A"], "dim_1": [0.1]})
        with pytest.raises(ValueError, match="missing columns"):
            build_panel(df)


# ---------------------------------------------------------------------------
# RegexNameExtendedStrategy — period classification from name tokens
# ---------------------------------------------------------------------------

from preprocessing.date_extractor import _classify_name_extended  # noqa: E402


class TestRegexNameExtendedStrategy:
    """Test the regex_name_extended date extraction strategy end-to-end."""

    _cfg = DateConfig(strategy="regex_name_extended")

    # ── Bronze Age ──────────────────────────────────────────────────────────

    def test_mlba_classifies_as_bronze_age(self):
        df = _make_df(["Israel_MLBA_o"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == -1800

    def test_mba_classifies_as_bronze_age(self):
        df = _make_df(["Turkey_MBA"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == -1800

    def test_eba_classifies_as_bronze_age(self):
        df = _make_df(["Turkey_EBA_II"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == -1800

    def test_lba_classifies_as_bronze_age(self):
        df = _make_df(["Anatolia_LBA_Sample"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == -1800

    def test_bronze_substring_classifies_as_bronze_age(self):
        df = _make_df(["Europe_BronzeAge"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == -1800

    # ── Iron Age ────────────────────────────────────────────────────────────

    def test_ia_classifies_as_iron_age(self):
        df = _make_df(["Turkey_IA_o4_noUDG"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == -800

    def test_eia_classifies_as_iron_age(self):
        df = _make_df(["Turkey_EIA_o"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == -800

    # ── Classical ───────────────────────────────────────────────────────────

    def test_roman_classifies_as_classical(self):
        df = _make_df(["Austria_Klosterneuburg_Roman_oLevant"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 0

    def test_hellenistic_classifies_as_classical(self):
        df = _make_df(["Turkey_Hellenistic"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 0

    def test_imperial_classifies_as_classical(self):
        df = _make_df(["Italy_Imperial_o1"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 0

    # ── Late Antiquity ───────────────────────────────────────────────────────

    def test_byzantine_classifies_as_late_antiquity(self):
        df = _make_df(["Turkey_Byzantine"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 500

    def test_earlybyzantine_classifies_as_late_antiquity(self):
        df = _make_df(["Turkey_EarlyByzantine_1_o"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 500

    def test_lateantiquity_classifies_as_late_antiquity(self):
        df = _make_df(["France_Sarrebourg_LateAntiquity_oLevant"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 500

    def test_romanbyzantine_classifies_as_late_antiquity_not_classical(self):
        """RomanByzantine must land in late_antiquity (Byzantine > Roman in priority)."""
        df = _make_df(["Turkey_RomanByzantine_3"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 500

    # ── Medieval ────────────────────────────────────────────────────────────

    def test_medieval_classifies_as_medieval(self):
        df = _make_df(["England_Medieval"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 1100

    def test_viking_classifies_as_medieval(self):
        df = _make_df(["Scandinavia_Viking"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 1100

    def test_emedieval_compound_classifies_as_medieval(self):
        df = _make_df(["Germany_EMedieval_Alemanic_SEurope"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 1100

    def test_postmedieval_classifies_as_medieval(self):
        df = _make_df(["Turkey_PostMedieval"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] == 1100

    # ── Fallback ─────────────────────────────────────────────────────────────

    def test_unrecognised_name_returns_none(self):
        df = _make_df(["Turkey_Ottoman"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] is None

    def test_country_only_returns_none(self):
        df = _make_df(["France"])
        dates = extract_dates(df, self._cfg)
        assert dates.iloc[0] is None

    def test_multiple_mixed_rows(self):
        df = _make_df([
            "Turkey_MBA",           # bronze_age   → -1800
            "Turkey_Byzantine",     # late_antiquity → 500
            "England_Medieval",     # medieval     →  1100
            "Turkey_Ottoman",       # unknown      →  None
        ])
        dates = extract_dates(df, self._cfg)
        assert list(dates) == [-1800, 500, 1100, None]

    # ── Split-by-period integration ──────────────────────────────────────────

    def test_split_produces_correct_buckets(self, tmp_path: Path):
        """Extended strategy + split_by_period routes rows to correct CSVs."""
        df = _make_df([
            "Turkey_MBA",
            "Turkey_IA_o",
            "Italy_Roman",
            "Turkey_EarlyByzantine_1",
            "England_Medieval",
            "Turkey_Ottoman",
        ])
        periods = {
            "bronze_age":     (-3300, -1200),
            "iron_age":       (-1200,  -500),
            "classical":      (  -500,  200),
            "late_antiquity": (   200,  800),
            "medieval":       (   800, 1500),
        }
        dates = extract_dates(df, self._cfg)
        buckets = split_by_period(df, dates, periods, output_dir=tmp_path)

        assert len(buckets["bronze_age"]) == 1
        assert len(buckets["iron_age"]) == 1
        assert len(buckets["classical"]) == 1
        assert len(buckets["late_antiquity"]) == 1
        assert len(buckets["medieval"]) == 1
        assert len(buckets["undated"]) == 1          # Ottoman
        assert len(buckets["out_of_range"]) == 0

        # CSVs written for every bucket
        assert (tmp_path / "bronze_age.csv").exists()
        assert (tmp_path / "iron_age.csv").exists()
        assert (tmp_path / "classical.csv").exists()
        assert (tmp_path / "late_antiquity.csv").exists()
        assert (tmp_path / "medieval.csv").exists()

    def test_ia_not_matched_as_substring_of_lateantiquity(self):
        """Ensure 'IA' exact-only match doesn't fire inside 'LateAntiquity'."""
        result = _classify_name_extended("Turkey_LateAntiquity_Sample")
        assert result == 500   # late_antiquity, not iron_age
