"""
tests/test_dual_mode.py — tests for dual-mode output (overall + per-period runs).

Covers:
  - run_dual_mode() directory structure
  - period_comparison.json content and structure
  - skipped period handling (missing file, empty file)
  - artifact_dir parameter on run_iterative()
  - ranked_by_distance ordering
  - overall run is independent of period runs
  - g25-dual-run CLI argument parsing
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine.result_parser import PopulationResult, RunResult
from optimizer.iteration_manager import run_iterations
from optimizer.scoring import OptimizationConfig
from orchestration.pipeline import (
    Config,
    DualModeResult,
    PeriodRunResult,
    _write_period_comparison,
    run_dual_mode,
    run_iterative,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIM_COLS = {f"dim_{i}": [float(i)] for i in range(1, 26)}


def _pool_df(names: list[str]) -> pd.DataFrame:
    rows = {f"dim_{i}": [float(i)] * len(names) for i in range(1, 26)}
    return pd.DataFrame({"name": names, **rows})


def _pool_csv(path: Path, names: list[str]) -> Path:
    _pool_df(names).to_csv(path, index=False)
    return path


def _target_csv(path: Path) -> Path:
    header = "name," + ",".join(f"dim_{i}" for i in range(1, 26))
    row = "Target," + ",".join(["0.0"] * 25)
    path.write_text(f"{header}\n{row}\n", encoding="utf-8")
    return path


def _html_for(dist: float, pops: list[tuple[str, float]]) -> str:
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


def _make_opt_config(**overrides) -> OptimizationConfig:
    defaults = dict(
        max_iterations=1,
        stop_distance=0.001,
        remove_percent_below=1.0,
        strong_percent_at_or_above=50.0,
        max_sources_per_panel=4,
        max_initial_panel_size=4,
    )
    defaults.update(overrides)
    return OptimizationConfig(**defaults)


def _make_pipeline_config(tmp_path: Path) -> Config:
    return Config(
        engine_path=tmp_path / "engine",
        engine_repo="https://example.com/fake",
        port=0,
        runs_dir=tmp_path / "runs",
        optimization=_make_opt_config(),
        profiles_dir=tmp_path / "profiles",
    )


def _stub_summary(tmp_path: Path, distance: float = 0.025, suffix: str = ""):
    """Build an IterationSummary via run_iterations with a stub runner."""
    pops = [("Italy_A", 60.0), ("Israel_B", 40.0)]
    pool = _pool_df([n for n, _ in pops])
    cfg = _make_opt_config()
    run_dir = tmp_path / f"stub_run{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    def runner(panel_text, target_text):
        return _html_for(distance, pops)

    return run_iterations(
        target_text="T," + ",".join(["0.0"] * 25),
        candidate_pool_df=pool,
        config=cfg,
        engine_runner=runner,
        artifact_dir=run_dir,
    ), run_dir


# ---------------------------------------------------------------------------
# artifact_dir parameter on run_iterative
# ---------------------------------------------------------------------------

class TestArtifactDir:
    def test_explicit_artifact_dir_used_instead_of_runs_dir(self, tmp_path: Path):
        """When artifact_dir is given, artifacts land there, not in runs_dir."""
        from unittest.mock import patch, MagicMock
        import pandas as pd

        config = _make_pipeline_config(tmp_path)
        explicit_dir = tmp_path / "my_explicit_dir"
        target_csv = _target_csv(tmp_path / "target.csv")
        pool_csv = _pool_csv(tmp_path / "pool.csv", ["Italy_A", "Israel_B"])

        pops = [("Italy_A", 60.0), ("Israel_B", 40.0)]

        with patch("orchestration.pipeline._ensure_engine"), \
             patch("orchestration.pipeline.LocalVahaduoServer") as mock_server, \
             patch("orchestration.pipeline.run_vahaduo") as mock_runner:

            mock_server.return_value.__enter__ = lambda s: "http://localhost:9999"
            mock_server.return_value.__exit__ = MagicMock(return_value=False)
            mock_runner.return_value = _html_for(0.025, pops)

            run_iterative(
                target_file=target_csv,
                candidate_pool_file=pool_csv,
                config=config,
                artifact_dir=explicit_dir,
            )

        # Artifacts must be in explicit_dir
        assert (explicit_dir / "best_result.json").exists()
        assert (explicit_dir / "meta.json").exists()
        # runs_dir must remain empty
        assert not any((tmp_path / "runs").iterdir()) if (tmp_path / "runs").exists() else True

    def test_no_artifact_dir_uses_runs_dir(self, tmp_path: Path):
        """When artifact_dir is None, a new directory under runs_dir is created."""
        from unittest.mock import patch, MagicMock

        config = _make_pipeline_config(tmp_path)
        target_csv = _target_csv(tmp_path / "target.csv")
        pool_csv = _pool_csv(tmp_path / "pool.csv", ["Italy_A", "Israel_B"])
        pops = [("Italy_A", 60.0), ("Israel_B", 40.0)]

        with patch("orchestration.pipeline._ensure_engine"), \
             patch("orchestration.pipeline.LocalVahaduoServer") as mock_server, \
             patch("orchestration.pipeline.run_vahaduo") as mock_runner:

            mock_server.return_value.__enter__ = lambda s: "http://localhost:9999"
            mock_server.return_value.__exit__ = MagicMock(return_value=False)
            mock_runner.return_value = _html_for(0.025, pops)

            run_iterative(
                target_file=target_csv,
                candidate_pool_file=pool_csv,
                config=config,
            )

        runs_dir = tmp_path / "runs"
        assert runs_dir.exists()
        run_dirs = list(runs_dir.iterdir())
        assert len(run_dirs) == 1
        assert (run_dirs[0] / "best_result.json").exists()


# ---------------------------------------------------------------------------
# _write_period_comparison
# ---------------------------------------------------------------------------

class TestWritePeriodComparison:
    def _make_summary(self, tmp_path: Path, distance: float, suffix: str = ""):
        summary, _ = _stub_summary(tmp_path, distance, suffix)
        return summary

    def test_creates_period_comparison_json(self, tmp_path: Path):
        overall = self._make_summary(tmp_path, 0.025, "o")
        period_results = [
            PeriodRunResult(
                period="classical", pool_file=tmp_path / "c.csv", pool_size=10,
                skipped=False, skip_reason="",
                best_distance=0.030, best_iteration=2,
                total_iterations=3, stop_reason="max_iterations reached (1)",
                summary=None,
            ),
        ]
        master_dir = tmp_path / "master"
        master_dir.mkdir()
        _write_period_comparison(master_dir, overall, period_results)
        assert (master_dir / "period_comparison.json").exists()

    def test_overall_distance_in_comparison(self, tmp_path: Path):
        overall = self._make_summary(tmp_path, 0.025, "o2")
        master_dir = tmp_path / "master2"
        master_dir.mkdir()
        _write_period_comparison(master_dir, overall, [])
        doc = json.loads((master_dir / "period_comparison.json").read_text())
        assert doc["overall_best_distance"] == pytest.approx(0.025)

    def test_period_entries_present(self, tmp_path: Path):
        overall = self._make_summary(tmp_path, 0.025, "o3")
        period_results = [
            PeriodRunResult(
                period="classical", pool_file=tmp_path / "c.csv", pool_size=5,
                skipped=False, skip_reason="",
                best_distance=0.030, best_iteration=1,
                total_iterations=1, stop_reason="done", summary=None,
            ),
            PeriodRunResult(
                period="medieval", pool_file=tmp_path / "m.csv", pool_size=3,
                skipped=False, skip_reason="",
                best_distance=0.040, best_iteration=1,
                total_iterations=1, stop_reason="done", summary=None,
            ),
        ]
        master_dir = tmp_path / "master3"
        master_dir.mkdir()
        _write_period_comparison(master_dir, overall, period_results)
        doc = json.loads((master_dir / "period_comparison.json").read_text())
        periods = {e["period"] for e in doc["period_results"]}
        assert "classical" in periods
        assert "medieval" in periods

    def test_ranked_by_distance_sorted_ascending(self, tmp_path: Path):
        overall = self._make_summary(tmp_path, 0.025, "o4")
        period_results = [
            PeriodRunResult("classical", tmp_path / "c.csv", 5, False, "",
                            0.040, 1, 1, "done", None),
            PeriodRunResult("medieval", tmp_path / "m.csv", 3, False, "",
                            0.030, 1, 1, "done", None),
            PeriodRunResult("late_antiquity", tmp_path / "l.csv", 4, False, "",
                            0.035, 1, 1, "done", None),
        ]
        master_dir = tmp_path / "master4"
        master_dir.mkdir()
        _write_period_comparison(master_dir, overall, period_results)
        doc = json.loads((master_dir / "period_comparison.json").read_text())
        distances = [e["best_distance"] for e in doc["ranked_by_distance"]]
        assert distances == sorted(distances)

    def test_skipped_period_recorded_with_skip_reason(self, tmp_path: Path):
        overall = self._make_summary(tmp_path, 0.025, "o5")
        period_results = [
            PeriodRunResult("classical", tmp_path / "c.csv", 0, True,
                            "pool file not found", None, None, None, None, None),
        ]
        master_dir = tmp_path / "master5"
        master_dir.mkdir()
        _write_period_comparison(master_dir, overall, period_results)
        doc = json.loads((master_dir / "period_comparison.json").read_text())
        entry = doc["period_results"][0]
        assert entry["skipped"] is True
        assert "pool file not found" in entry["skip_reason"]

    def test_skipped_period_excluded_from_ranked_list(self, tmp_path: Path):
        overall = self._make_summary(tmp_path, 0.025, "o6")
        period_results = [
            PeriodRunResult("classical", tmp_path / "c.csv", 5, False, "",
                            0.030, 1, 1, "done", None),
            PeriodRunResult("medieval", tmp_path / "m.csv", 0, True,
                            "empty pool", None, None, None, None, None),
        ]
        master_dir = tmp_path / "master6"
        master_dir.mkdir()
        _write_period_comparison(master_dir, overall, period_results)
        doc = json.loads((master_dir / "period_comparison.json").read_text())
        ranked_periods = [e["period"] for e in doc["ranked_by_distance"]]
        assert "medieval" not in ranked_periods
        assert "classical" in ranked_periods

    def test_no_periods_produces_empty_ranked_list(self, tmp_path: Path):
        overall = self._make_summary(tmp_path, 0.025, "o7")
        master_dir = tmp_path / "master7"
        master_dir.mkdir()
        _write_period_comparison(master_dir, overall, [])
        doc = json.loads((master_dir / "period_comparison.json").read_text())
        assert doc["ranked_by_distance"] == []
        assert doc["period_results"] == []


# ---------------------------------------------------------------------------
# run_dual_mode directory structure
# ---------------------------------------------------------------------------

class TestDualModeStructure:
    def test_overall_subdir_created(self, tmp_path: Path):
        from unittest.mock import patch, MagicMock

        config = _make_pipeline_config(tmp_path)
        target = _target_csv(tmp_path / "t.csv")
        overall_pool = _pool_csv(tmp_path / "overall.csv", ["Italy_A", "Israel_B"])
        pops = [("Italy_A", 60.0), ("Israel_B", 40.0)]

        with patch("orchestration.pipeline._ensure_engine"), \
             patch("orchestration.pipeline.LocalVahaduoServer") as ms, \
             patch("orchestration.pipeline.run_vahaduo") as mr:
            ms.return_value.__enter__ = lambda s: "http://localhost:9999"
            ms.return_value.__exit__ = MagicMock(return_value=False)
            mr.return_value = _html_for(0.025, pops)

            result = run_dual_mode(
                target_file=target,
                overall_pool_file=overall_pool,
                period_pool_files={},
                config=config,
            )

        assert (result.master_dir / "overall").exists()

    def test_period_comparison_json_created(self, tmp_path: Path):
        from unittest.mock import patch, MagicMock

        config = _make_pipeline_config(tmp_path)
        target = _target_csv(tmp_path / "t.csv")
        overall_pool = _pool_csv(tmp_path / "overall.csv", ["Italy_A", "Israel_B"])
        pops = [("Italy_A", 60.0), ("Israel_B", 40.0)]

        with patch("orchestration.pipeline._ensure_engine"), \
             patch("orchestration.pipeline.LocalVahaduoServer") as ms, \
             patch("orchestration.pipeline.run_vahaduo") as mr:
            ms.return_value.__enter__ = lambda s: "http://localhost:9999"
            ms.return_value.__exit__ = MagicMock(return_value=False)
            mr.return_value = _html_for(0.025, pops)

            result = run_dual_mode(
                target_file=target,
                overall_pool_file=overall_pool,
                period_pool_files={},
                config=config,
            )

        assert (result.master_dir / "period_comparison.json").exists()

    def test_missing_period_pool_is_skipped(self, tmp_path: Path):
        from unittest.mock import patch, MagicMock

        config = _make_pipeline_config(tmp_path)
        target = _target_csv(tmp_path / "t.csv")
        overall_pool = _pool_csv(tmp_path / "overall.csv", ["Italy_A", "Israel_B"])
        pops = [("Italy_A", 60.0), ("Israel_B", 40.0)]

        with patch("orchestration.pipeline._ensure_engine"), \
             patch("orchestration.pipeline.LocalVahaduoServer") as ms, \
             patch("orchestration.pipeline.run_vahaduo") as mr:
            ms.return_value.__enter__ = lambda s: "http://localhost:9999"
            ms.return_value.__exit__ = MagicMock(return_value=False)
            mr.return_value = _html_for(0.025, pops)

            result = run_dual_mode(
                target_file=target,
                overall_pool_file=overall_pool,
                period_pool_files={"classical": tmp_path / "nonexistent.csv"},
                config=config,
            )

        assert len(result.period_results) == 1
        assert result.period_results[0].skipped is True
        assert "not found" in result.period_results[0].skip_reason

    def test_empty_period_pool_is_skipped(self, tmp_path: Path):
        from unittest.mock import patch, MagicMock

        config = _make_pipeline_config(tmp_path)
        target = _target_csv(tmp_path / "t.csv")
        overall_pool = _pool_csv(tmp_path / "overall.csv", ["Italy_A", "Israel_B"])
        empty_pool = tmp_path / "empty.csv"
        empty_pool.write_text("name," + ",".join(f"dim_{i}" for i in range(1, 26)) + "\n",
                              encoding="utf-8")
        pops = [("Italy_A", 60.0), ("Israel_B", 40.0)]

        with patch("orchestration.pipeline._ensure_engine"), \
             patch("orchestration.pipeline.LocalVahaduoServer") as ms, \
             patch("orchestration.pipeline.run_vahaduo") as mr:
            ms.return_value.__enter__ = lambda s: "http://localhost:9999"
            ms.return_value.__exit__ = MagicMock(return_value=False)
            mr.return_value = _html_for(0.025, pops)

            result = run_dual_mode(
                target_file=target,
                overall_pool_file=overall_pool,
                period_pool_files={"classical": empty_pool},
                config=config,
            )

        assert result.period_results[0].skipped is True
        assert "empty" in result.period_results[0].skip_reason

    def test_overall_summary_returned(self, tmp_path: Path):
        from unittest.mock import patch, MagicMock

        config = _make_pipeline_config(tmp_path)
        target = _target_csv(tmp_path / "t.csv")
        overall_pool = _pool_csv(tmp_path / "overall.csv", ["Italy_A", "Israel_B"])
        pops = [("Italy_A", 60.0), ("Israel_B", 40.0)]

        with patch("orchestration.pipeline._ensure_engine"), \
             patch("orchestration.pipeline.LocalVahaduoServer") as ms, \
             patch("orchestration.pipeline.run_vahaduo") as mr:
            ms.return_value.__enter__ = lambda s: "http://localhost:9999"
            ms.return_value.__exit__ = MagicMock(return_value=False)
            mr.return_value = _html_for(0.025, pops)

            result = run_dual_mode(
                target_file=target,
                overall_pool_file=overall_pool,
                period_pool_files={},
                config=config,
            )

        assert result.overall_summary is not None
        assert result.overall_summary.best_record.result.distance == pytest.approx(0.025)

    def test_master_dir_inside_runs_dir(self, tmp_path: Path):
        from unittest.mock import patch, MagicMock

        config = _make_pipeline_config(tmp_path)
        target = _target_csv(tmp_path / "t.csv")
        overall_pool = _pool_csv(tmp_path / "overall.csv", ["Italy_A", "Israel_B"])
        pops = [("Italy_A", 60.0), ("Israel_B", 40.0)]

        with patch("orchestration.pipeline._ensure_engine"), \
             patch("orchestration.pipeline.LocalVahaduoServer") as ms, \
             patch("orchestration.pipeline.run_vahaduo") as mr:
            ms.return_value.__enter__ = lambda s: "http://localhost:9999"
            ms.return_value.__exit__ = MagicMock(return_value=False)
            mr.return_value = _html_for(0.025, pops)

            result = run_dual_mode(
                target_file=target,
                overall_pool_file=overall_pool,
                period_pool_files={},
                config=config,
            )

        assert result.master_dir.parent == config.runs_dir


# ---------------------------------------------------------------------------
# g25-dual-run CLI argument parsing
# ---------------------------------------------------------------------------

class TestDualRunCli:
    def _parse(self, argv: list[str]):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("target")
        parser.add_argument("overall_pool")
        parser.add_argument("--config", default=None)
        parser.add_argument("--profile", default=None, metavar="PROFILE_NAME")
        parser.add_argument("--periods-dir", default=None, metavar="DIR")
        return parser.parse_args(argv)

    def test_target_and_overall_pool_captured(self):
        args = self._parse(["t.csv", "overall.csv"])
        assert args.target == "t.csv"
        assert args.overall_pool == "overall.csv"

    def test_profile_defaults_to_none(self):
        args = self._parse(["t.csv", "p.csv"])
        assert args.profile is None

    def test_profile_flag_captured(self):
        args = self._parse(["t.csv", "p.csv", "--profile", "eastmed_europe"])
        assert args.profile == "eastmed_europe"

    def test_periods_dir_defaults_to_none(self):
        args = self._parse(["t.csv", "p.csv"])
        assert args.periods_dir is None

    def test_periods_dir_captured(self):
        args = self._parse(["t.csv", "p.csv", "--periods-dir", "data/candidate_pools"])
        assert args.periods_dir == "data/candidate_pools"

    def test_cmd_dual_run_importable(self):
        from scripts.cli import cmd_dual_run
        assert callable(cmd_dual_run)

    def test_help_exits_cleanly(self):
        from scripts.cli import cmd_dual_run
        with pytest.raises(SystemExit) as exc:
            cmd_dual_run(["--help"])
        assert exc.value.code == 0

    def test_missing_args_exits_with_error(self):
        from scripts.cli import cmd_dual_run
        with pytest.raises(SystemExit) as exc:
            cmd_dual_run([])
        assert exc.value.code != 0

    def test_nonexistent_target_exits_with_error(self, tmp_path: Path):
        from scripts.cli import cmd_dual_run
        with pytest.raises(SystemExit) as exc:
            cmd_dual_run(["nonexistent.csv", "pool.csv"])
        assert exc.value.code != 0

    def test_nonexistent_overall_pool_exits_with_error(self, tmp_path: Path):
        from scripts.cli import cmd_dual_run
        target = tmp_path / "t.csv"
        target.write_text("name,dim_1\nT,0.1\n")
        with pytest.raises(SystemExit) as exc:
            cmd_dual_run([str(target), "nonexistent_pool.csv"])
        assert exc.value.code != 0
