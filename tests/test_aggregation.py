"""tests/test_aggregation.py — unit tests for optimizer/aggregation.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.result_parser import PopulationResult, RunResult
from optimizer.aggregation import AggregatedPopulation, aggregate_by_prefix
from optimizer.iteration_manager import run_iterations
from optimizer.scoring import OptimizationConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(pops: list[tuple[str, float]]) -> RunResult:
    return RunResult(
        distance=0.05,
        populations=[PopulationResult(name=n, percent=p) for n, p in pops],
        raw_output="<fake>",
    )


def _html_for(distance: float, pops: list[tuple[str, float]]) -> str:
    rows = "".join(
        f'<tr><td class="singleleftcolumn">{pct}</td>'
        f'<td class="singlerightcolumn">{name}</td></tr>'
        for name, pct in pops
    )
    return (
        f"<table><tr><th>Target: T<br/>"
        f"Distance: {distance * 100:.4f}% / {distance:.8f}</th></tr>"
        f"{rows}</table>"
    )


def _make_config(**overrides) -> OptimizationConfig:
    defaults = dict(
        max_iterations=3,
        stop_distance=0.001,
        remove_percent_below=1.0,
        strong_percent_at_or_above=50.0,
        max_sources_per_panel=4,
        max_initial_panel_size=4,
    )
    defaults.update(overrides)
    return OptimizationConfig(**defaults)


def _make_pool(names: list[str]):
    import pandas as pd
    dims = {f"dim_{i}": [float(i)] * len(names) for i in range(1, 26)}
    return pd.DataFrame({"name": names, **dims})


# ---------------------------------------------------------------------------
# aggregate_by_prefix
# ---------------------------------------------------------------------------

class TestAggregateByPrefix:
    def test_single_population_single_region(self):
        result = aggregated = aggregate_by_prefix(_result([("Israel_MLBA_o", 100.0)]))
        assert len(aggregated) == 1
        assert aggregated[0].region == "Israel"
        assert aggregated[0].percent == pytest.approx(100.0)

    def test_two_populations_same_prefix_summed(self):
        r = _result([("Italy_Imperial_o1", 26.4), ("Italy_Sardinia_Roman", 15.4)])
        agg = aggregate_by_prefix(r)
        assert len(agg) == 1
        assert agg[0].region == "Italy"
        assert agg[0].percent == pytest.approx(41.8)

    def test_multiple_prefixes_separate_entries(self):
        r = _result([
            ("Israel_MLBA_o", 28.6),
            ("Italy_Imperial_o1.SG", 26.4),
            ("Italy_Sardinia_Roman_o", 15.4),
            ("Croatia_SisakPogorelec_Roman.SG", 12.4),
            ("Turkey_EarlyByzantine_1", 10.8),
            ("Croatia_NovoSeloBunje_Roman.SG", 6.4),
        ])
        agg = aggregate_by_prefix(r)
        regions = {a.region: a.percent for a in agg}
        assert regions["Italy"] == pytest.approx(41.8)
        assert regions["Israel"] == pytest.approx(28.6)
        assert regions["Croatia"] == pytest.approx(18.8, abs=0.01)
        assert regions["Turkey"] == pytest.approx(10.8)

    def test_sorted_descending_by_percent(self):
        r = _result([
            ("Turkey_A", 10.0),
            ("Italy_A", 50.0),
            ("Israel_A", 40.0),
        ])
        agg = aggregate_by_prefix(r)
        percents = [a.percent for a in agg]
        assert percents == sorted(percents, reverse=True)

    def test_prefix_extracted_at_first_underscore(self):
        r = _result([("Multi_Part_Name_Here", 100.0)])
        agg = aggregate_by_prefix(r)
        assert agg[0].region == "Multi"

    def test_name_with_no_underscore(self):
        """Population with no underscore uses full name as prefix."""
        r = _result([("Denisovan", 100.0)])
        agg = aggregate_by_prefix(r)
        assert agg[0].region == "Denisovan"

    def test_empty_populations(self):
        r = _result([])
        assert aggregate_by_prefix(r) == []

    def test_percent_rounded_to_two_decimal_places(self):
        r = _result([("Italy_A", 10.333), ("Italy_B", 20.667)])
        agg = aggregate_by_prefix(r)
        assert agg[0].percent == pytest.approx(31.0, abs=0.01)

    def test_returns_list_of_aggregated_population(self):
        r = _result([("Israel_A", 100.0)])
        agg = aggregate_by_prefix(r)
        assert all(isinstance(a, AggregatedPopulation) for a in agg)


# ---------------------------------------------------------------------------
# aggregated_result.json artifact
# ---------------------------------------------------------------------------

class TestAggregatedArtifact:
    def test_artifact_written(self, tmp_path: Path):
        pool = _make_pool(["Italy_A", "Israel_B", "Croatia_C", "Turkey_D"])
        cfg = _make_config(max_iterations=1)

        def runner(panel_text, target_text):
            return _html_for(0.05, [
                ("Italy_A", 60.0), ("Israel_B", 25.0),
                ("Croatia_C", 10.0), ("Turkey_D", 5.0),
            ])

        run_iterations("T," + ",".join(["0.0"] * 25), pool, cfg, runner, tmp_path)
        assert (tmp_path / "aggregated_result.json").exists()

    def test_artifact_structure(self, tmp_path: Path):
        pool = _make_pool(["Italy_A", "Italy_B", "Israel_C", "Croatia_D"])
        cfg = _make_config(max_iterations=1)

        def runner(panel_text, target_text):
            return _html_for(0.05, [
                ("Italy_A", 40.0), ("Italy_B", 20.0),
                ("Israel_C", 25.0), ("Croatia_D", 15.0),
            ])

        run_iterations("T," + ",".join(["0.0"] * 25), pool, cfg, runner, tmp_path)
        data = json.loads((tmp_path / "aggregated_result.json").read_text())

        assert "distance" in data
        assert "by_country" in data
        regions = {e["region"]: e["percent"] for e in data["by_country"]}
        assert regions["Italy"] == pytest.approx(60.0)
        assert regions["Israel"] == pytest.approx(25.0)
        assert regions["Croatia"] == pytest.approx(15.0)

    def test_artifact_sorted_descending(self, tmp_path: Path):
        pool = _make_pool(["A_x", "B_x", "C_x", "D_x"])
        cfg = _make_config(max_iterations=1)

        def runner(panel_text, target_text):
            return _html_for(0.05, [
                ("A_x", 10.0), ("B_x", 50.0), ("C_x", 30.0), ("D_x", 10.0),
            ])

        run_iterations("T," + ",".join(["0.0"] * 25), pool, cfg, runner, tmp_path)
        data = json.loads((tmp_path / "aggregated_result.json").read_text())
        percents = [e["percent"] for e in data["by_country"]]
        assert percents == sorted(percents, reverse=True)

    def test_artifact_distance_matches_best(self, tmp_path: Path):
        """aggregated_result.json distance matches best_result.json distance."""
        pool = _make_pool(["Italy_A", "Israel_B"])
        cfg = _make_config(max_iterations=1)

        def runner(panel_text, target_text):
            return _html_for(0.03456789, [("Italy_A", 70.0), ("Israel_B", 30.0)])

        run_iterations("T," + ",".join(["0.0"] * 25), pool, cfg, runner, tmp_path)
        agg = json.loads((tmp_path / "aggregated_result.json").read_text())
        best = json.loads((tmp_path / "best_result.json").read_text())
        assert agg["distance"] == best["distance"]
