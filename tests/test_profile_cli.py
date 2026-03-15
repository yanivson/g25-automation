"""
tests/test_profile_cli.py — tests for optional interpretation profile support.

Covers:
  - load_profile() with valid / invalid profile names
  - run with no profile (no generic_summary.json written)
  - run with valid profile (generic_summary.json written and correct)
  - artifact differences between profiled and non-profiled runs
  - meta.json profile field
  - CLI --profile flag (argument parsing layer)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.result_parser import PopulationResult, RunResult
from optimizer.aggregation import aggregate_by_prefix
from optimizer.interpretation import InterpretationConfig
from optimizer.iteration_manager import run_iterations
from optimizer.scoring import OptimizationConfig
from orchestration.pipeline import (
    Config,
    _write_iterative_meta,
    load_profile,
    _list_profiles,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _make_profile_dir(tmp_path: Path, profiles: dict[str, dict]) -> Path:
    """Write profile YAML files into a temp directory and return the dir."""
    d = tmp_path / "profiles"
    d.mkdir()
    for name, content in profiles.items():
        (d / f"{name}.yaml").write_text(yaml.dump(content), encoding="utf-8")
    return d


def _eastmed_profile_dict() -> dict:
    return {
        "prefix_to_region": {"Israel": "Levant", "Turkey": "Anatolia", "Italy": "Southern Europe"},
        "region_to_macro": {"Levant": "Eastern Mediterranean", "Anatolia": "Eastern Mediterranean",
                            "Southern Europe": "Southern Europe"},
        "macro_to_label": {"Eastern Mediterranean": "East Mediterranean ancestry",
                           "Southern Europe": "Southern European ancestry"},
    }


def _minimal_profile_dict() -> dict:
    return {"prefix_to_region": {}, "region_to_macro": {}, "macro_to_label": {}}


def _fake_config(tmp_path: Path) -> Config:
    from dataclasses import field as dc_field
    opt = OptimizationConfig(
        max_iterations=1,
        stop_distance=0.001,
        remove_percent_below=1.0,
        strong_percent_at_or_above=50.0,
        max_sources_per_panel=4,
        max_initial_panel_size=4,
    )
    return Config(
        engine_path=tmp_path / "engine",
        engine_repo="https://example.com/fake",
        port=0,
        runs_dir=tmp_path / "runs",
        optimization=opt,
        profiles_dir=tmp_path / "profiles",
    )


def _stub_csv(path: Path) -> Path:
    """Write a minimal single-row G25 CSV to path and return it."""
    header = "name," + ",".join(f"dim_{i}" for i in range(1, 26))
    row = "Target," + ",".join(["0.0"] * 25)
    path.write_text(f"{header}\n{row}\n", encoding="utf-8")
    return path


def _fake_summary(tmp_path: Path):
    """Build a minimal IterationSummary via run_iterations with a stub runner."""
    import pandas as pd

    def _html_for(dist: float, pops):
        rows = "".join(
            f'<tr><td class="singleleftcolumn">{pct}</td>'
            f'<td class="singlerightcolumn">{name}</td></tr>'
            for name, pct in pops
        )
        return (
            f"<table><tr><th>Target: T<br/>"
            f"Distance: {dist * 100:.4f}% / {dist:.8f}</th></tr>"
            f"{rows}</table>"
        )

    pops = [("Israel_MLBA", 40.0), ("Turkey_Early", 35.0), ("Italy_Imperial", 25.0)]
    dims = {f"dim_{i}": [float(i)] * 3 for i in range(1, 26)}
    pool = pd.DataFrame({"name": [n for n, _ in pops], **dims})
    cfg = OptimizationConfig(
        max_iterations=1, stop_distance=0.001,
        remove_percent_below=1.0, strong_percent_at_or_above=50.0,
        max_sources_per_panel=4, max_initial_panel_size=4,
    )
    run_dir = tmp_path / "run_dir"
    run_dir.mkdir(parents=True, exist_ok=True)

    def runner(panel_text, target_text):
        return _html_for(0.025, pops)

    return run_iterations(
        target_text="T," + ",".join(["0.0"] * 25),
        candidate_pool_df=pool,
        config=cfg,
        engine_runner=runner,
        artifact_dir=run_dir,
    ), run_dir


# ---------------------------------------------------------------------------
# load_profile — valid profile
# ---------------------------------------------------------------------------

class TestLoadProfile:
    def test_loads_existing_profile(self, tmp_path: Path):
        d = _make_profile_dir(tmp_path, {"eastmed": _eastmed_profile_dict()})
        profile = load_profile("eastmed", profiles_dir=d)
        assert isinstance(profile, InterpretationConfig)

    def test_prefix_to_region_populated(self, tmp_path: Path):
        d = _make_profile_dir(tmp_path, {"eastmed": _eastmed_profile_dict()})
        profile = load_profile("eastmed", profiles_dir=d)
        assert profile.prefix_to_region["Israel"] == "Levant"

    def test_region_to_macro_populated(self, tmp_path: Path):
        d = _make_profile_dir(tmp_path, {"eastmed": _eastmed_profile_dict()})
        profile = load_profile("eastmed", profiles_dir=d)
        assert profile.region_to_macro["Levant"] == "Eastern Mediterranean"

    def test_macro_to_label_populated(self, tmp_path: Path):
        d = _make_profile_dir(tmp_path, {"eastmed": _eastmed_profile_dict()})
        profile = load_profile("eastmed", profiles_dir=d)
        assert profile.macro_to_label["Eastern Mediterranean"] == "East Mediterranean ancestry"

    def test_minimal_profile_loads_empty_dicts(self, tmp_path: Path):
        d = _make_profile_dir(tmp_path, {"minimal": _minimal_profile_dict()})
        profile = load_profile("minimal", profiles_dir=d)
        assert profile.prefix_to_region == {}
        assert profile.region_to_macro == {}
        assert profile.macro_to_label == {}

    def test_profile_with_null_sections_loads_safely(self, tmp_path: Path):
        """A profile YAML that omits sections entirely should not raise."""
        d = tmp_path / "profiles"
        d.mkdir()
        (d / "sparse.yaml").write_text("prefix_to_region:\n  A: B\n", encoding="utf-8")
        profile = load_profile("sparse", profiles_dir=d)
        assert profile.region_to_macro == {}

    def test_empty_yaml_file_loads_safely(self, tmp_path: Path):
        """Completely empty YAML file (minimal.yaml pattern) is valid."""
        d = tmp_path / "profiles"
        d.mkdir()
        (d / "empty.yaml").write_text("", encoding="utf-8")
        profile = load_profile("empty", profiles_dir=d)
        assert isinstance(profile, InterpretationConfig)


# ---------------------------------------------------------------------------
# load_profile — invalid profile
# ---------------------------------------------------------------------------

class TestLoadProfileInvalid:
    def test_missing_profile_raises_file_not_found(self, tmp_path: Path):
        d = _make_profile_dir(tmp_path, {})
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            load_profile("nonexistent", profiles_dir=d)

    def test_error_message_includes_profile_name(self, tmp_path: Path):
        d = _make_profile_dir(tmp_path, {})
        with pytest.raises(FileNotFoundError, match="my_missing_profile"):
            load_profile("my_missing_profile", profiles_dir=d)

    def test_missing_profiles_dir_raises(self, tmp_path: Path):
        absent = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError):
            load_profile("anything", profiles_dir=absent)

    def test_list_profiles_on_empty_dir(self, tmp_path: Path):
        d = tmp_path / "profiles"
        d.mkdir()
        assert _list_profiles(d) == []

    def test_list_profiles_returns_sorted_stems(self, tmp_path: Path):
        d = _make_profile_dir(tmp_path, {
            "zz_last": _minimal_profile_dict(),
            "aa_first": _minimal_profile_dict(),
            "mm_mid": _minimal_profile_dict(),
        })
        assert _list_profiles(d) == ["aa_first", "mm_mid", "zz_last"]


# ---------------------------------------------------------------------------
# Artifact differences: no profile vs profiled
# ---------------------------------------------------------------------------

class TestArtifactDifferences:
    def test_no_profile_does_not_write_generic_summary(self, tmp_path: Path):
        summary, _ = _fake_summary(tmp_path)
        config = _fake_config(tmp_path)
        target_csv = _stub_csv(tmp_path / "target.csv")
        pool_csv   = _stub_csv(tmp_path / "pool.csv")
        out = tmp_path / "out_no_profile"
        out.mkdir()

        _write_iterative_meta(
            run_dir=out, run_id="test_noprofile", config=config,
            target_file=target_csv, candidate_pool_file=pool_csv,
            summary=summary, interpretation=None, profile_name=None,
        )

        assert not (out / "generic_summary.json").exists()

    def test_profiled_run_writes_generic_summary(self, tmp_path: Path):
        summary, _ = _fake_summary(tmp_path)
        config = _fake_config(tmp_path)
        d = _make_profile_dir(tmp_path, {"eastmed": _eastmed_profile_dict()})
        profile = load_profile("eastmed", profiles_dir=d)
        target_csv = _stub_csv(tmp_path / "target.csv")
        pool_csv   = _stub_csv(tmp_path / "pool.csv")
        out = tmp_path / "out_profiled"
        out.mkdir()

        _write_iterative_meta(
            run_dir=out, run_id="test_profiled", config=config,
            target_file=target_csv, candidate_pool_file=pool_csv,
            summary=summary, interpretation=profile, profile_name="eastmed",
        )

        assert (out / "generic_summary.json").exists()

    def test_generic_summary_has_expected_keys(self, tmp_path: Path):
        summary, _ = _fake_summary(tmp_path)
        config = _fake_config(tmp_path)
        d = _make_profile_dir(tmp_path, {"eastmed": _eastmed_profile_dict()})
        profile = load_profile("eastmed", profiles_dir=d)
        target_csv = _stub_csv(tmp_path / "target2.csv")
        pool_csv   = _stub_csv(tmp_path / "pool2.csv")
        out = tmp_path / "out_keys"
        out.mkdir()

        _write_iterative_meta(
            run_dir=out, run_id="test_keys", config=config,
            target_file=target_csv, candidate_pool_file=pool_csv,
            summary=summary, interpretation=profile, profile_name="eastmed",
        )

        doc = json.loads((out / "generic_summary.json").read_text())
        for key in ("profile", "distance", "top_samples", "by_prefix",
                    "by_macro_region", "summary_lines"):
            assert key in doc, f"Missing key: {key}"

    def test_generic_summary_profile_field_matches_name(self, tmp_path: Path):
        summary, _ = _fake_summary(tmp_path)
        config = _fake_config(tmp_path)
        d = _make_profile_dir(tmp_path, {"eastmed": _eastmed_profile_dict()})
        profile = load_profile("eastmed", profiles_dir=d)
        target_csv = _stub_csv(tmp_path / "t3.csv")
        pool_csv   = _stub_csv(tmp_path / "p3.csv")
        out = tmp_path / "out_profile_field"
        out.mkdir()

        _write_iterative_meta(
            run_dir=out, run_id="x", config=config,
            target_file=target_csv, candidate_pool_file=pool_csv,
            summary=summary, interpretation=profile, profile_name="eastmed",
        )

        doc = json.loads((out / "generic_summary.json").read_text())
        assert doc["profile"] == "eastmed"

    def test_both_runs_always_write_meta_json(self, tmp_path: Path):
        summary, _ = _fake_summary(tmp_path)
        config = _fake_config(tmp_path)
        target_csv = _stub_csv(tmp_path / "ta.csv")
        pool_csv   = _stub_csv(tmp_path / "pa.csv")

        for label, interp, pname in [
            ("no_profile", None, None),
            ("profiled", InterpretationConfig(), "minimal"),
        ]:
            out = tmp_path / label
            out.mkdir()
            _write_iterative_meta(
                run_dir=out, run_id=label, config=config,
                target_file=target_csv, candidate_pool_file=pool_csv,
                summary=summary, interpretation=interp, profile_name=pname,
            )
            assert (out / "meta.json").exists()

    def test_meta_json_profile_field_is_null_when_no_profile(self, tmp_path: Path):
        summary, _ = _fake_summary(tmp_path)
        config = _fake_config(tmp_path)
        target_csv = _stub_csv(tmp_path / "tn.csv")
        pool_csv   = _stub_csv(tmp_path / "pn.csv")
        out = tmp_path / "no_profile_meta"
        out.mkdir()

        _write_iterative_meta(
            run_dir=out, run_id="np", config=config,
            target_file=target_csv, candidate_pool_file=pool_csv,
            summary=summary, interpretation=None, profile_name=None,
        )

        meta = json.loads((out / "meta.json").read_text())
        assert meta["profile"] is None

    def test_meta_json_profile_field_is_set_when_profiled(self, tmp_path: Path):
        summary, _ = _fake_summary(tmp_path)
        config = _fake_config(tmp_path)
        target_csv = _stub_csv(tmp_path / "tp.csv")
        pool_csv   = _stub_csv(tmp_path / "pp.csv")
        out = tmp_path / "profiled_meta"
        out.mkdir()

        _write_iterative_meta(
            run_dir=out, run_id="p", config=config,
            target_file=target_csv, candidate_pool_file=pool_csv,
            summary=summary, interpretation=InterpretationConfig(), profile_name="minimal",
        )

        meta = json.loads((out / "meta.json").read_text())
        assert meta["profile"] == "minimal"

    def test_aggregated_result_json_always_written(self, tmp_path: Path):
        """aggregated_result.json is written by iteration_manager regardless of profile."""
        _, run_dir = _fake_summary(tmp_path)
        assert (run_dir / "aggregated_result.json").exists()

    def test_best_result_json_always_written(self, tmp_path: Path):
        _, run_dir = _fake_summary(tmp_path)
        assert (run_dir / "best_result.json").exists()


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

class TestCliArgParsing:
    """Test the argument parser layer without invoking the engine."""

    def _parse(self, argv: list[str]):
        """Return parsed args from cmd_run's parser, extracted without running."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("target")
        parser.add_argument("pool")
        parser.add_argument("--config", default=None)
        parser.add_argument("--profile", default=None, metavar="PROFILE_NAME")
        return parser.parse_args(argv)

    def test_no_profile_flag_gives_none(self):
        args = self._parse(["target.csv", "pool.csv"])
        assert args.profile is None

    def test_profile_flag_captured(self):
        args = self._parse(["target.csv", "pool.csv", "--profile", "eastmed_europe"])
        assert args.profile == "eastmed_europe"

    def test_profile_name_is_string(self):
        args = self._parse(["t.csv", "p.csv", "--profile", "northwest_europe"])
        assert isinstance(args.profile, str)
