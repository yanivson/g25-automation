"""
Tests for final_report.json generation — build_final_report and write_final_report.
Appended to test_interpreter.py coverage via a separate module to avoid file-append
complexity; imported symbols are re-used from the same packages.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from interpretation.evidence_pack import (
    build_evidence_from_run_dir,
    build_evidence_pack,
)
from interpretation.interpreter import (
    build_final_report,
    run_interpretation,
    write_final_report,
)

_BY_COUNTRY = [
    {"region": "Italy", "percent": 42.0},
    {"region": "Greece", "percent": 30.0},
    {"region": "Turkey", "percent": 28.0},
]
_TOP_SAMPLES = [
    {"name": "ITA_Roman", "percent": 42.0},
    {"name": "GRC_Classical", "percent": 30.0},
]
_BY_MACRO = [
    {"macro_region": "Southern Europe", "percent": 72.0, "label": "dominant"},
    {"macro_region": "Anatolia", "percent": 28.0, "label": ""},
]


def _make_pack(**kwargs):
    defaults = dict(
        run_id="test_run",
        best_distance=0.025,
        by_country=_BY_COUNTRY,
        top_samples=_TOP_SAMPLES,
        by_macro_region=_BY_MACRO,
        period_comparison=[],
        profile_name="eastmed_europe",
        user_id="yaniv",
        display_name="Yaniv",
        identity_context="Ashkenazi Jewish",
        ydna_haplogroup="I-Y38863",
    )
    defaults.update(kwargs)
    return build_evidence_pack(**defaults)


def _make_run_dir(tmp_path, *, with_generic=False, with_period=False):
    run_dir = tmp_path / "run_xyz"
    run_dir.mkdir()
    meta = {
        "run_id": "run_xyz",
        "best_distance": 0.028,
        "profile": "eastmed_europe",
        "best_iteration": 2,
        "stop_reason": "panel_repeat_streak=2 >= stop_if_panel_repeats=2",
    }
    (run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    agg = {"by_country": _BY_COUNTRY, "top_samples": _TOP_SAMPLES}
    (run_dir / "aggregated_result.json").write_text(json.dumps(agg), encoding="utf-8")
    if with_generic:
        (run_dir / "generic_summary.json").write_text(
            json.dumps({"by_macro_region": _BY_MACRO}), encoding="utf-8"
        )
    if with_period:
        pc = {"period_results": [
            {"period": "classical", "best_distance": 0.033, "skipped": False},
            {"period": "bronze_age", "best_distance": 0.0, "skipped": True},
        ]}
        (run_dir / "period_comparison.json").write_text(json.dumps(pc), encoding="utf-8")
    return run_dir


class TestBuildFinalReport:
    def test_top_level_keys(self):
        report = build_final_report(_make_pack())
        assert set(report.keys()) == {
            "user", "run", "by_country", "by_macro_region",
            "top_samples", "periods", "artifacts",
        }

    def test_user_section(self):
        u = build_final_report(_make_pack())["user"]
        assert u["user_id"] == "yaniv"
        assert u["display_name"] == "Yaniv"
        assert u["identity_context"] == "Ashkenazi Jewish"
        assert u["ydna_haplogroup"] == "I-Y38863"

    def test_user_section_null_when_no_profile(self):
        pack = _make_pack(user_id=None, display_name=None,
                          identity_context=None, ydna_haplogroup=None)
        u = build_final_report(pack)["user"]
        assert u["user_id"] is None
        assert u["display_name"] is None

    def test_run_section_fields(self):
        pack = _make_pack(best_distance=0.025, best_iteration=3,
                          stop_reason="panel_repeat_streak=2")
        r = build_final_report(pack)["run"]
        assert r["run_id"] == "test_run"
        assert r["profile"] == "eastmed_europe"
        assert r["best_distance"] == pytest.approx(0.025)
        assert r["distance_quality"] == "close fit"
        assert r["best_iteration"] == 3
        assert r["stop_reason"] == "panel_repeat_streak=2"

    def test_run_section_null_iteration_when_absent(self):
        pack = _make_pack()
        r = build_final_report(pack)["run"]
        assert r["best_iteration"] is None
        assert r["stop_reason"] is None

    def test_by_country_forwarded(self):
        assert build_final_report(_make_pack())["by_country"] == _BY_COUNTRY

    def test_by_macro_region_forwarded(self):
        assert build_final_report(_make_pack())["by_macro_region"] == _BY_MACRO

    def test_by_macro_region_empty_when_absent(self):
        assert build_final_report(_make_pack(by_macro_region=[]))["by_macro_region"] == []

    def test_top_samples_forwarded(self):
        assert build_final_report(_make_pack())["top_samples"] == _TOP_SAMPLES

    def test_periods_empty_when_no_dual_run(self):
        report = build_final_report(_make_pack(period_comparison=[]))
        assert report["periods"]["best_period"] is None
        assert report["periods"]["comparison"] == []

    def test_periods_with_data(self):
        comparison = [
            {"period": "classical", "best_distance": 0.030, "skipped": False},
            {"period": "bronze_age", "best_distance": 0.0, "skipped": True},
        ]
        report = build_final_report(_make_pack(period_comparison=comparison))
        assert report["periods"]["best_period"] == "classical"
        assert len(report["periods"]["comparison"]) == 2

    def test_artifacts_always_has_evidence_pack(self):
        assert build_final_report(_make_pack())["artifacts"]["evidence_pack_json"] == "evidence_pack.json"

    def test_artifacts_best_result_and_aggregated(self):
        a = build_final_report(_make_pack())["artifacts"]
        assert a["best_result_json"] == "best_result.json"
        assert a["aggregated_result_json"] == "aggregated_result.json"

    def test_artifacts_generic_null_without_profile(self):
        pack = build_evidence_pack(
            run_id="x", best_distance=0.030,
            by_country=_BY_COUNTRY, top_samples=_TOP_SAMPLES,
        )
        assert build_final_report(pack)["artifacts"]["generic_summary_json"] is None

    def test_artifacts_period_null_without_dual_run(self):
        assert build_final_report(_make_pack())["artifacts"]["period_comparison_json"] is None

    def test_pure_function_deterministic(self):
        pack = _make_pack(best_iteration=1, stop_reason="stop_distance")
        assert build_final_report(pack) == build_final_report(pack)


class TestWriteFinalReport:
    def test_writes_file(self, tmp_path):
        out = write_final_report(_make_pack(), tmp_path)
        assert out.exists()
        assert out.name == "final_report.json"

    def test_json_valid(self, tmp_path):
        write_final_report(_make_pack(), tmp_path)
        data = json.loads((tmp_path / "final_report.json").read_text(encoding="utf-8"))
        assert "user" in data and "run" in data

    def test_run_interpretation_writes_final_report(self, tmp_path):
        run_interpretation(tmp_path, _make_pack())
        assert (tmp_path / "final_report.json").exists()

    def test_all_three_artifacts_written(self, tmp_path):
        run_interpretation(tmp_path, _make_pack())
        assert (tmp_path / "evidence_pack.json").exists()
        assert (tmp_path / "final_report.json").exists()
        assert (tmp_path / "interpretation_status.json").exists()

    def test_best_iteration_from_meta(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        pack = build_evidence_from_run_dir(run_dir)
        run_interpretation(run_dir, pack)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["run"]["best_iteration"] == 2

    def test_stop_reason_from_meta(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        pack = build_evidence_from_run_dir(run_dir)
        run_interpretation(run_dir, pack)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert "panel_repeat_streak" in data["run"]["stop_reason"]

    def test_consistency_with_evidence_pack(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, with_generic=True)
        pack = build_evidence_from_run_dir(run_dir)
        run_interpretation(run_dir, pack)
        ep = json.loads((run_dir / "evidence_pack.json").read_text(encoding="utf-8"))
        fr = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert fr["run"]["run_id"] == ep["run_id"]
        assert fr["run"]["best_distance"] == ep["best_distance"]
        assert fr["run"]["distance_quality"] == ep["distance_quality"]
        assert fr["by_country"] == ep["by_country"]
        assert fr["top_samples"] == ep["top_samples"]

    def test_with_generic_summary(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, with_generic=True)
        pack = build_evidence_from_run_dir(run_dir)
        run_interpretation(run_dir, pack)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert len(data["by_macro_region"]) == 2
        assert data["artifacts"]["generic_summary_json"] == "generic_summary.json"

    def test_without_generic_summary(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, with_generic=False)
        pack = build_evidence_from_run_dir(run_dir)
        run_interpretation(run_dir, pack)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["by_macro_region"] == []
        assert data["artifacts"]["generic_summary_json"] is None

    def test_with_period_comparison(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, with_period=True)
        pack = build_evidence_from_run_dir(run_dir)
        run_interpretation(run_dir, pack)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["periods"]["best_period"] == "classical"
        assert len(data["periods"]["comparison"]) == 2
        assert data["artifacts"]["period_comparison_json"] == "period_comparison.json"

    def test_without_period_comparison(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, with_period=False)
        pack = build_evidence_from_run_dir(run_dir)
        run_interpretation(run_dir, pack)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["periods"]["best_period"] is None
        assert data["periods"]["comparison"] == []
        assert data["artifacts"]["period_comparison_json"] is None

    def test_user_metadata_from_user_folder(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        pack = build_evidence_from_run_dir(
            run_dir,
            user_id="yaniv",
            display_name="Yaniv",
            identity_context="Ashkenazi Jewish",
            ydna_haplogroup="I-Y38863",
        )
        run_interpretation(run_dir, pack)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        u = data["user"]
        assert u["user_id"] == "yaniv"
        assert u["display_name"] == "Yaniv"
        assert u["identity_context"] == "Ashkenazi Jewish"
        assert u["ydna_haplogroup"] == "I-Y38863"

    def test_user_metadata_null_when_no_user_folder(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        pack = build_evidence_from_run_dir(run_dir)  # no user kwargs
        run_interpretation(run_dir, pack)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"]["user_id"] is None
        assert data["user"]["display_name"] is None
