"""
tests/test_period_diagnostics.py — Tests for period diagnostics integration.

Coverage:
  - _normalize_period_doc handles real pipeline format (period_results + best_distance)
  - _normalize_period_doc handles legacy format (periods + distance)
  - _normalize_period_doc returns None for empty data
  - _normalize_period_doc skips skipped periods
  - run_period_diagnostics writes period_comparison.json to output_dir
  - overall_distance recorded when provided
  - render_report includes period explanatory text
  - render_report dynamic sentence names best period
  - overall best distance unchanged by period diagnostics doc
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from report.make_report import _normalize_period_doc
from report.templates import render_report


# ---------------------------------------------------------------------------
# _normalize_period_doc — format normalisation
# ---------------------------------------------------------------------------

_REAL_FORMAT = {
    "overall_best_distance": 0.024,
    "overall_best_iteration": 1,
    "overall_stop_reason": "pool exhausted",
    "period_results": [
        {
            "period": "classical",
            "pool_file": "data/classical_pool.csv",
            "pool_size": 16,
            "skipped": False,
            "best_distance": 0.031,
            "best_iteration": 1,
            "total_iterations": 1,
            "stop_reason": "pool exhausted",
        },
        {
            "period": "late_antiquity",
            "pool_file": "data/late_antiquity_pool.csv",
            "pool_size": 15,
            "skipped": False,
            "best_distance": 0.025,
            "best_iteration": 1,
            "total_iterations": 1,
            "stop_reason": "pool exhausted",
        },
        {
            "period": "medieval",
            "pool_file": "data/medieval_pool.csv",
            "pool_size": 0,
            "skipped": True,
            "skip_reason": "empty pool",
        },
    ],
    "ranked_by_distance": [
        {"period": "late_antiquity", "best_distance": 0.025},
        {"period": "classical",      "best_distance": 0.031},
    ],
}

_LEGACY_FORMAT = {
    "periods": [
        {"period": "classical",    "distance": 0.031},
        {"period": "late_antiquity","distance": 0.025},
    ],
    "best_period": "late_antiquity",
}


class TestNormalizePeriodDoc:
    def test_real_format_returns_periods_list(self):
        result = _normalize_period_doc(_REAL_FORMAT)
        assert result is not None
        assert "periods" in result
        assert len(result["periods"]) == 2  # skipped medieval excluded

    def test_real_format_uses_best_distance_key(self):
        result = _normalize_period_doc(_REAL_FORMAT)
        assert result is not None
        for p in result["periods"]:
            assert "distance" in p
            assert "best_distance" not in p

    def test_real_format_best_period_from_ranked(self):
        result = _normalize_period_doc(_REAL_FORMAT)
        assert result is not None
        assert result["best_period"] == "late_antiquity"

    def test_real_format_skipped_periods_excluded(self):
        result = _normalize_period_doc(_REAL_FORMAT)
        assert result is not None
        names = [p["period"] for p in result["periods"]]
        assert "medieval" not in names

    def test_legacy_format_passes_through(self):
        result = _normalize_period_doc(_LEGACY_FORMAT)
        assert result is not None
        assert result["best_period"] == "late_antiquity"
        assert len(result["periods"]) == 2

    def test_empty_period_results_returns_none(self):
        doc = {"period_results": [], "ranked_by_distance": []}
        assert _normalize_period_doc(doc) is None

    def test_empty_periods_key_returns_none(self):
        assert _normalize_period_doc({"periods": []}) is None

    def test_all_skipped_returns_none(self):
        doc = {
            "period_results": [
                {"period": "classical", "pool_file": "x", "pool_size": 0,
                 "skipped": True, "skip_reason": "empty pool"},
            ],
            "ranked_by_distance": [],
        }
        assert _normalize_period_doc(doc) is None


# ---------------------------------------------------------------------------
# render_report — period explanatory text
# ---------------------------------------------------------------------------

_PROFILE = {
    "user_id": "u1",
    "display_name": "Test",
    "identity_context": "Test Context",
    "ydna_haplogroup": "R1b",
}
_FINAL_REPORT = {
    "run": {
        "run_id": "r1", "profile": "p1",
        "best_distance": 0.024, "distance_quality": "close fit",
        "best_iteration": 1, "stop_reason": "streak",
    },
    "by_country": [{"region": "Italy", "percent": 60.0}, {"region": "Israel", "percent": 40.0}],
    "by_macro_region": [{"macro_region": "S Europe", "percent": 60.0, "label": "S Europe"}],
    "top_samples": [{"name": "Italy_Roman_o", "percent": 60.0}],
    "periods": {"best_period": None, "comparison": []},
    "artifacts": {},
}
_AGGREGATED = {"distance": 0.024, "by_country": _FINAL_REPORT["by_country"], "top_samples": _FINAL_REPORT["top_samples"]}


def _render(period_data=None):
    return render_report(
        profile=_PROFILE,
        final_report=_FINAL_REPORT,
        aggregated=_AGGREGATED,
        generic_summary=None,
        period_data=period_data,
        interpretation=None,
    )


class TestPeriodExplanatoryText:
    def test_no_period_card_when_no_data(self):
        # Compact card hidden when no period data
        html = _render(period_data=None)
        assert "Historical Period Signal" not in html

    def test_no_data_message_in_appendix_when_no_period_data(self):
        html = _render(period_data=None)
        assert "not generated" in html

    def test_period_signal_card_shown_with_data(self):
        html = _render(period_data=_LEGACY_FORMAT)
        assert "Historical Period Signal" in html

    def test_period_signal_card_fixed_note(self):
        html = _render(period_data=_LEGACY_FORMAT)
        assert "closest single-period approximation" in html
        assert "primary result" in html

    def test_period_signal_card_names_best_period(self):
        html = _render(period_data=_LEGACY_FORMAT)
        assert "Late Antiquity" in html

    def test_period_detail_shows_other_periods_in_appendix(self):
        # Other period names appear in the appendix detail block
        html = _render(period_data=_LEGACY_FORMAT)
        assert "Classical" in html

    def test_overall_distance_not_changed_by_period_doc(self):
        # The overall best distance from final_report must appear unchanged
        html = _render(period_data=_REAL_FORMAT)
        assert "0.024" in html  # overall distance
        # Both period distances also appear in appendix detail
        assert "0.031" in html
        assert "0.025" in html


# ---------------------------------------------------------------------------
# run_period_diagnostics — output file test (lightweight: no engine needed)
# ---------------------------------------------------------------------------

class TestRunPeriodDiagnosticsOutput:
    """
    Verify period_comparison.json is written with the correct structure
    when all pool files are missing (all skipped).
    Uses no engine / no browser — purely tests the file-writing path.
    """

    def test_all_skipped_writes_json(self, tmp_path):
        from orchestration.pipeline import run_period_diagnostics, load_config

        config = load_config(Path("config.yaml"))
        # Point to non-existent pools so all periods are skipped
        fake_pools = {
            "classical":     tmp_path / "classical_pool.csv",
            "late_antiquity": tmp_path / "late_antiquity_pool.csv",
        }
        target = Path("data/users/yaniv/input/target.csv")
        if not target.exists():
            pytest.skip("yaniv target file not available")

        run_period_diagnostics(
            target_file=target,
            period_pool_files=fake_pools,
            config=config,
            output_dir=tmp_path,
            overall_distance=0.024,
        )

        out = tmp_path / "period_comparison.json"
        assert out.exists()
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert "period_results" in doc
        assert "ranked_by_distance" in doc
        assert doc["overall_best_distance"] == 0.024
        # All periods skipped (files don't exist)
        for entry in doc["period_results"]:
            assert entry["skipped"] is True

    def test_period_comparison_written_to_output_dir(self, tmp_path):
        from orchestration.pipeline import run_period_diagnostics, load_config

        config = load_config(Path("config.yaml"))
        target = Path("data/users/yaniv/input/target.csv")
        if not target.exists():
            pytest.skip("yaniv target file not available")

        run_period_diagnostics(
            target_file=target,
            period_pool_files={},   # empty — no periods to run
            config=config,
            output_dir=tmp_path,
        )
        # Even with zero periods it writes the file
        assert (tmp_path / "period_comparison.json").exists()
