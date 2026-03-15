"""tests/test_optimizer.py — unit tests for optimizer modules.

All tests are fully offline — no Playwright, no local server required.
The engine_runner is a mock callable that returns deterministic HTML strings.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from engine.result_parser import PopulationResult, RunResult
from optimizer.scoring import (
    OptimizationConfig,
    PanelClassification,
    classify_result,
    should_stop,
)
from optimizer.panel_mutation import (
    MutationState,
    apply_mutation,
    build_initial_panel_df,
    panel_df_to_text,
)
from optimizer.iteration_manager import run_iterations, IterationSummary


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> OptimizationConfig:
    defaults = dict(
        max_iterations=10,
        stop_distance=0.01,
        remove_percent_below=1.0,
        strong_percent_at_or_above=10.0,
        max_sources_per_panel=5,
        max_initial_panel_size=6,
    )
    defaults.update(overrides)
    return OptimizationConfig(**defaults)


def _make_result(distance: float, pops: list[tuple[str, float]]) -> RunResult:
    """Build a RunResult with given distance and (name, percent) pairs."""
    return RunResult(
        distance=distance,
        populations=[PopulationResult(name=n, percent=p) for n, p in pops],
        raw_output="<fake>",
    )


def _make_pool(names: list[str]) -> pd.DataFrame:
    """Build a minimal 26-column candidate pool DataFrame."""
    dims = {f"dim_{i}": [float(i)] * len(names) for i in range(1, 26)}
    return pd.DataFrame({"name": names, **dims})


def _make_classification(
    strong: list[str] | None = None,
    surviving: list[str] | None = None,
    weak: list[str] | None = None,
) -> PanelClassification:
    return PanelClassification(
        strong=strong or [],
        surviving=surviving or [],
        weak=weak or [],
    )


# ---------------------------------------------------------------------------
# scoring.classify_result
# ---------------------------------------------------------------------------

class TestClassifyResult:
    cfg = _make_config(remove_percent_below=1.0, strong_percent_at_or_above=10.0)

    def test_strong_classification(self):
        result = _make_result(0.05, [("PopA", 50.0)])
        cl = classify_result(result, self.cfg)
        assert "PopA" in cl.strong
        assert "PopA" not in cl.surviving
        assert "PopA" not in cl.weak

    def test_weak_classification(self):
        result = _make_result(0.05, [("PopA", 0.5)])
        cl = classify_result(result, self.cfg)
        assert "PopA" in cl.weak
        assert "PopA" not in cl.strong

    def test_surviving_classification(self):
        result = _make_result(0.05, [("PopA", 5.0)])
        cl = classify_result(result, self.cfg)
        assert "PopA" in cl.surviving
        assert "PopA" not in cl.strong
        assert "PopA" not in cl.weak

    def test_exact_strong_threshold(self):
        """Population exactly at strong threshold is classified as strong."""
        result = _make_result(0.05, [("PopA", 10.0)])
        cl = classify_result(result, self.cfg)
        assert "PopA" in cl.strong

    def test_exact_remove_threshold(self):
        """Population exactly at remove threshold is classified as surviving (not weak)."""
        result = _make_result(0.05, [("PopA", 1.0)])
        cl = classify_result(result, self.cfg)
        assert "PopA" in cl.surviving

    def test_mixed_classification(self):
        result = _make_result(0.05, [
            ("Strong_A", 40.0),
            ("Surviving_B", 5.0),
            ("Weak_C", 0.1),
        ])
        cl = classify_result(result, self.cfg)
        assert cl.strong == ["Strong_A"]
        assert cl.surviving == ["Surviving_B"]
        assert cl.weak == ["Weak_C"]

    def test_keep_contains_strong_and_surviving(self):
        result = _make_result(0.05, [("S", 50.0), ("V", 5.0), ("W", 0.5)])
        cl = classify_result(result, self.cfg)
        assert set(cl.keep) == {"S", "V"}

    def test_remove_contains_only_weak(self):
        result = _make_result(0.05, [("S", 50.0), ("V", 5.0), ("W", 0.5)])
        cl = classify_result(result, self.cfg)
        assert cl.remove == ["W"]


# ---------------------------------------------------------------------------
# scoring.should_stop
# ---------------------------------------------------------------------------

class TestShouldStop:
    cfg = _make_config(max_iterations=5, stop_distance=0.01)

    def _result(self, distance: float) -> RunResult:
        return _make_result(distance, [("A", 100.0)])

    def test_stop_on_distance(self):
        stop, reason = should_stop(self._result(0.005), iteration=1, config=self.cfg)
        assert stop is True
        assert "stop_distance" in reason

    def test_no_stop_above_distance(self):
        stop, _ = should_stop(self._result(0.05), iteration=1, config=self.cfg)
        assert stop is False

    def test_stop_on_panel_unchanged(self):
        stop, reason = should_stop(
            self._result(0.05), iteration=1, config=self.cfg, panel_unchanged=True
        )
        assert stop is True
        assert "converged" in reason

    def test_stop_on_pool_exhausted(self):
        stop, reason = should_stop(
            self._result(0.05), iteration=1, config=self.cfg, pool_exhausted=True
        )
        assert stop is True
        assert "exhausted" in reason

    def test_stop_on_max_iterations(self):
        stop, reason = should_stop(self._result(0.05), iteration=5, config=self.cfg)
        assert stop is True
        assert "max_iterations" in reason

    def test_no_stop_before_max(self):
        stop, _ = should_stop(self._result(0.05), iteration=4, config=self.cfg)
        assert stop is False

    def test_distance_stop_takes_priority(self):
        """Distance stop fires even when panel_unchanged is True."""
        stop, reason = should_stop(
            self._result(0.005), iteration=1, config=self.cfg, panel_unchanged=True
        )
        assert "stop_distance" in reason

    # -- Streak-based stop conditions ----------------------------------------

    def test_stop_on_no_improvement_streak(self):
        cfg = _make_config(max_iterations=20, stop_distance=0.01,
                           stop_if_no_improvement_iterations=3)
        stop, reason = should_stop(
            self._result(0.05), iteration=2, config=cfg, no_improvement_streak=3
        )
        assert stop is True
        assert "no_improvement_streak" in reason

    def test_no_stop_below_no_improvement_threshold(self):
        cfg = _make_config(max_iterations=20, stop_distance=0.01,
                           stop_if_no_improvement_iterations=3)
        stop, _ = should_stop(
            self._result(0.05), iteration=2, config=cfg, no_improvement_streak=2
        )
        assert stop is False

    def test_no_improvement_disabled_when_zero(self):
        """stop_if_no_improvement_iterations=0 never triggers."""
        cfg = _make_config(max_iterations=20, stop_distance=0.01,
                           stop_if_no_improvement_iterations=0)
        stop, _ = should_stop(
            self._result(0.05), iteration=2, config=cfg, no_improvement_streak=999
        )
        assert stop is False

    def test_stop_on_panel_repeat_streak(self):
        cfg = _make_config(max_iterations=20, stop_distance=0.01,
                           stop_if_panel_repeats=2)
        stop, reason = should_stop(
            self._result(0.05), iteration=3, config=cfg, panel_repeat_streak=2
        )
        assert stop is True
        assert "panel_repeat_streak" in reason

    def test_no_stop_below_panel_repeat_threshold(self):
        cfg = _make_config(max_iterations=20, stop_distance=0.01,
                           stop_if_panel_repeats=2)
        stop, _ = should_stop(
            self._result(0.05), iteration=3, config=cfg, panel_repeat_streak=1
        )
        assert stop is False

    def test_panel_repeat_disabled_when_zero(self):
        cfg = _make_config(max_iterations=20, stop_distance=0.01,
                           stop_if_panel_repeats=0)
        stop, _ = should_stop(
            self._result(0.05), iteration=3, config=cfg, panel_repeat_streak=999
        )
        assert stop is False

    def test_stop_on_zero_new_candidates_streak(self):
        cfg = _make_config(max_iterations=20, stop_distance=0.01,
                           stop_if_all_new_candidates_zero=2)
        stop, reason = should_stop(
            self._result(0.05), iteration=3, config=cfg, zero_new_candidates_streak=2
        )
        assert stop is True
        assert "zero_new_candidates_streak" in reason

    def test_no_stop_below_zero_new_candidates_threshold(self):
        cfg = _make_config(max_iterations=20, stop_distance=0.01,
                           stop_if_all_new_candidates_zero=2)
        stop, _ = should_stop(
            self._result(0.05), iteration=3, config=cfg, zero_new_candidates_streak=1
        )
        assert stop is False

    def test_zero_new_candidates_disabled_when_zero(self):
        cfg = _make_config(max_iterations=20, stop_distance=0.01,
                           stop_if_all_new_candidates_zero=0)
        stop, _ = should_stop(
            self._result(0.05), iteration=3, config=cfg, zero_new_candidates_streak=999
        )
        assert stop is False

    def test_distance_beats_no_improvement_streak(self):
        """Distance stop fires before streak conditions."""
        cfg = _make_config(max_iterations=20, stop_distance=0.01,
                           stop_if_no_improvement_iterations=1)
        stop, reason = should_stop(
            self._result(0.005), iteration=2, config=cfg, no_improvement_streak=5
        )
        assert "stop_distance" in reason


# ---------------------------------------------------------------------------
# panel_mutation.build_initial_panel_df
# ---------------------------------------------------------------------------

class TestBuildInitialPanel:
    def test_returns_all_when_under_cap(self):
        pool = _make_pool(["A", "B", "C"])
        cfg = _make_config(max_initial_panel_size=5)
        result = build_initial_panel_df(pool, cfg)
        assert len(result) == 3

    def test_caps_at_max_initial_panel_size(self):
        pool = _make_pool(["A", "B", "C", "D", "E"])
        cfg = _make_config(max_initial_panel_size=3)
        result = build_initial_panel_df(pool, cfg)
        assert len(result) == 3

    def test_selection_is_by_sorted_name(self):
        pool = _make_pool(["C", "A", "B"])
        cfg = _make_config(max_initial_panel_size=2)
        result = build_initial_panel_df(pool, cfg)
        # Should pick "A" and "B" (first 2 sorted alphabetically)
        assert set(result["name"].tolist()) == {"A", "B"}


# ---------------------------------------------------------------------------
# panel_mutation.apply_mutation
# ---------------------------------------------------------------------------

class TestApplyMutation:
    cfg = _make_config(max_sources_per_panel=4)

    def test_weak_moved_to_exhausted(self):
        pool = _make_pool(["A", "B", "C", "D", "E"])
        cl = _make_classification(strong=["A"], surviving=["B"], weak=["C"])
        state = MutationState(candidate_pool_names=sorted(pool["name"].tolist()))
        apply_mutation(cl, state, pool, self.cfg)
        assert "C" in state.exhausted_set

    def test_strong_always_preserved(self):
        pool = _make_pool(["A", "B", "C"])
        cl = _make_classification(strong=["A"], weak=["B", "C"])
        state = MutationState(candidate_pool_names=sorted(pool["name"].tolist()))
        mut = apply_mutation(cl, state, pool, self.cfg)
        assert "A" in mut.next_panel_df["name"].tolist()

    def test_max_panel_size_enforced(self):
        pool = _make_pool(["A", "B", "C", "D", "E", "F"])
        # Keep 2, fill up to 4
        cl = _make_classification(surviving=["A", "B"])
        state = MutationState(candidate_pool_names=sorted(pool["name"].tolist()))
        mut = apply_mutation(cl, state, pool, self.cfg)
        assert len(mut.next_panel_df) <= 4

    def test_exhausted_not_readded(self):
        pool = _make_pool(["A", "B", "C", "D"])
        cl = _make_classification(surviving=["A"], weak=["B"])
        state = MutationState(
            candidate_pool_names=sorted(pool["name"].tolist()),
            exhausted_set={"B"},
        )
        mut = apply_mutation(cl, state, pool, self.cfg)
        assert "B" not in mut.next_panel_df["name"].tolist()

    def test_fill_candidates_sorted(self):
        pool = _make_pool(["A", "B", "C", "D", "E"])
        cl = _make_classification(surviving=["A"])  # 3 slots to fill
        state = MutationState(candidate_pool_names=sorted(pool["name"].tolist()))
        mut = apply_mutation(cl, state, pool, self.cfg)
        # Fill should pick B, C, D (sorted, A is already kept)
        names = mut.next_panel_df["name"].tolist()
        assert "B" in names
        assert "C" in names

    def test_panel_unchanged_detected(self):
        pool = _make_pool(["A", "B"])
        # Only 2 pops in pool and both are kept — no candidates to add
        cl = _make_classification(strong=["A", "B"])
        state = MutationState(candidate_pool_names=["A", "B"])
        mut = apply_mutation(cl, state, pool, self.cfg)
        assert mut.panel_unchanged is True

    def test_panel_changed_when_new_fill(self):
        pool = _make_pool(["A", "B", "C"])
        cl = _make_classification(surviving=["A"], weak=["B"])
        state = MutationState(candidate_pool_names=["A", "B", "C"])
        mut = apply_mutation(cl, state, pool, self.cfg)
        assert mut.panel_unchanged is False


# ---------------------------------------------------------------------------
# iteration_manager.run_iterations (with mock engine_runner)
# ---------------------------------------------------------------------------

def _html_for(distance: float, pops: list[tuple[str, float]]) -> str:
    """Build minimal singleFMC-style HTML for a given result."""
    rows = "".join(
        f'<tr><td class="singleleftcolumn">{pct}</td>'
        f'<td class="singlerightcolumn">{name}</td></tr>'
        for name, pct in pops
    )
    return (
        f"<table><tr><th>Target: T<br/>"
        f"Distance: {distance*100:.4f}% / {distance:.8f}</th></tr>"
        f"{rows}</table>"
    )


class TestRunIterations:
    cfg = _make_config(
        max_iterations=5,
        stop_distance=0.01,
        remove_percent_below=1.0,
        strong_percent_at_or_above=50.0,
        max_sources_per_panel=4,
        max_initial_panel_size=4,
    )

    def _pool(self) -> pd.DataFrame:
        return _make_pool(["A", "B", "C", "D", "E", "F"])

    def test_stops_on_distance(self, tmp_path: Path):
        """Runner that always returns a good distance stops on first iteration."""
        calls = []
        def runner(panel_text, target_text):
            calls.append(panel_text)
            return _html_for(0.005, [("A", 60.0), ("B", 40.0)])

        summary = run_iterations("T,0.1", self._pool(), self.cfg, runner, tmp_path)
        assert summary.total_iterations == 1
        assert "stop_distance" in summary.stop_reason
        assert len(calls) == 1

    def test_stops_on_max_iterations(self, tmp_path: Path):
        """Runner that always returns a poor distance runs until max_iterations."""
        def runner(panel_text, target_text):
            return _html_for(0.05, [("A", 60.0), ("B", 35.0), ("C", 4.0), ("D", 0.5)])

        summary = run_iterations("T,0.1", self._pool(), self.cfg, runner, tmp_path)
        assert summary.total_iterations == self.cfg.max_iterations

    def test_best_record_is_lowest_distance(self, tmp_path: Path):
        """Best record tracks the iteration with minimum distance."""
        distances = [0.08, 0.04, 0.06, 0.09, 0.07]
        call_idx = [0]
        def runner(panel_text, target_text):
            d = distances[call_idx[0] % len(distances)]
            call_idx[0] += 1
            return _html_for(d, [("A", 60.0), ("B", 40.0)])

        summary = run_iterations("T,0.1", self._pool(), self.cfg, runner, tmp_path)
        assert summary.best_record.result.distance == min(
            r.result.distance for r in summary.records
        )

    def test_threshold_removal_reduces_panel(self, tmp_path: Path):
        """Weak populations are removed from subsequent panels."""
        call_idx = [0]
        def runner(panel_text, target_text):
            call_idx[0] += 1
            if call_idx[0] == 1:
                # First run: D is weak (0.5%)
                return _html_for(0.05, [("A", 60.0), ("B", 30.0), ("C", 9.0), ("D", 0.5)])
            # Subsequent: D should not be present
            if "D," in panel_text or "\nD\n" in panel_text or panel_text.startswith("D"):
                raise AssertionError("Weak population D was re-added to panel")
            return _html_for(0.05, [("A", 60.0), ("B", 30.0), ("C", 9.0)])

        run_iterations("T,0.1", self.pool_without_e_f(), self.cfg, runner, tmp_path)

    def pool_without_e_f(self) -> pd.DataFrame:
        return _make_pool(["A", "B", "C", "D"])

    def test_strong_preserved_across_iterations(self, tmp_path: Path):
        """Strong populations (>=50%) are never removed."""
        call_idx = [0]
        def runner(panel_text, target_text):
            call_idx[0] += 1
            return _html_for(0.05, [("A", 60.0), ("B", 35.0), ("C", 4.9)])

        summary = run_iterations("T,0.1", _make_pool(["A", "B", "C"]), self.cfg, runner, tmp_path)
        # A is always strong (60%) — it must appear in every iteration's panel
        for record in summary.records:
            panel_names = {line.split(",")[0] for line in record.panel_text.strip().splitlines()}
            assert "A" in panel_names

    def test_per_iteration_artifacts_written(self, tmp_path: Path):
        """Artifact files are written for each iteration."""
        def runner(panel_text, target_text):
            return _html_for(0.05, [("A", 60.0), ("B", 40.0)])

        summary = run_iterations("T,0.1", self.pool_without_e_f(), self.cfg, runner, tmp_path)
        for i in range(1, summary.total_iterations + 1):
            prefix = f"iteration_{i:02d}"
            assert (tmp_path / f"{prefix}_panel.txt").exists()
            assert (tmp_path / f"{prefix}_raw_output.txt").exists()
            assert (tmp_path / f"{prefix}_result.json").exists()

    def test_best_result_json_written(self, tmp_path: Path):
        """best_result.json is written and contains the best iteration's data."""
        def runner(panel_text, target_text):
            return _html_for(0.005, [("A", 60.0), ("B", 40.0)])

        run_iterations("T,0.1", self.pool_without_e_f(), self.cfg, runner, tmp_path)
        best_path = tmp_path / "best_result.json"
        assert best_path.exists()
        data = json.loads(best_path.read_text())
        assert "distance" in data
        assert "populations" in data
        assert "iteration" in data
        assert data["distance"] > 0

    def test_result_json_per_iteration_parseable(self, tmp_path: Path):
        """Each iteration_NN_result.json has the expected diagnostic fields and a valid distance."""
        def runner(panel_text, target_text):
            return _html_for(0.05, [("A", 60.0), ("B", 40.0)])

        summary = run_iterations("T,0.1", self.pool_without_e_f(), self.cfg, runner, tmp_path)
        for i in range(1, summary.total_iterations + 1):
            path = tmp_path / f"iteration_{i:02d}_result.json"
            data = json.loads(path.read_text())
            assert data["distance"] > 0
            assert "populations" in data
            assert "strong_count" in data
            assert "weak_count" in data
            assert "removed_names" in data
            assert "added_names" in data

    def test_run_summary_json_written(self, tmp_path: Path):
        """run_summary.json is written and contains expected top-level keys."""
        def runner(panel_text, target_text):
            return _html_for(0.05, [("A", 60.0), ("B", 40.0)])

        run_iterations("T,0.1", self.pool_without_e_f(), self.cfg, runner, tmp_path)
        summary_path = tmp_path / "run_summary.json"
        assert summary_path.exists()
        data = json.loads(summary_path.read_text())
        for key in (
            "distance_by_iteration", "best_distance", "best_iteration",
            "stop_reason", "total_iterations", "exhausted_count",
            "final_panel_size", "all_removed", "all_added", "iteration_diagnostics",
        ):
            assert key in data, f"Missing key: {key}"

    def test_run_summary_distances_match_iteration_jsons(self, tmp_path: Path):
        """run_summary.json distances match the individual iteration_NN_result.json values."""
        distances_seq = [0.08, 0.04, 0.06, 0.09, 0.07]
        call_idx = [0]
        def runner(panel_text, target_text):
            d = distances_seq[call_idx[0] % len(distances_seq)]
            call_idx[0] += 1
            return _html_for(d, [("A", 60.0), ("B", 40.0)])

        summary = run_iterations("T,0.1", self.pool_without_e_f(), self.cfg, runner, tmp_path)
        run_summary = json.loads((tmp_path / "run_summary.json").read_text())

        for i in range(1, summary.total_iterations + 1):
            iter_data = json.loads((tmp_path / f"iteration_{i:02d}_result.json").read_text())
            assert run_summary["distance_by_iteration"][i - 1] == iter_data["distance"]

    def test_exhausted_set_accumulates_across_iterations(self, tmp_path: Path):
        """Populations removed as weak in iteration 1 are not re-added in later iterations."""
        # D gets 0.5% (weak) in iteration 1; subsequent iterations must not include D in panel
        call_idx = [0]
        def runner(panel_text, target_text):
            call_idx[0] += 1
            if call_idx[0] == 1:
                return _html_for(0.05, [("A", 60.0), ("B", 30.0), ("C", 9.0), ("D", 0.5)])
            # D should never appear again; its absence is enforced by exhausted_set
            return _html_for(0.05, [("A", 60.0), ("B", 30.0), ("C", 9.0)])

        summary = run_iterations("T,0.1", _make_pool(["A", "B", "C", "D"]), self.cfg, runner, tmp_path)

        # D should appear in all_removed exactly once
        assert summary.all_removed.count("D") == 1

        # D must not appear in any panel text after iteration 1
        for record in summary.records[1:]:
            panel_names = {line.split(",")[0] for line in record.panel_text.strip().splitlines()}
            assert "D" not in panel_names, f"D reappeared in iteration {record.iteration} panel"

    def test_deterministic_refill_ordering(self, tmp_path: Path):
        """Fill candidates are always drawn in sorted-name order from the available pool."""
        # Panel has A (surviving), B (weak removed). Pool has C, D, E as fresh candidates.
        # After B is exhausted, fill should pick C first (sorted), then D.
        call_idx = [0]
        def runner(panel_text, target_text):
            call_idx[0] += 1
            if call_idx[0] == 1:
                # A=surviving, B=weak; cfg max_sources_per_panel=4, so 3 fill slots
                return _html_for(0.05, [("A", 5.0), ("B", 0.5), ("C", 60.0), ("D", 34.5)])
            return _html_for(0.05, [("A", 60.0), ("C", 40.0)])

        pool = _make_pool(["A", "B", "C", "D", "E"])
        summary = run_iterations("T,0.1", pool, self.cfg, runner, tmp_path)

        # Iteration 1's added_names should be in sorted order (C, D were in panel from initial)
        # Iteration 2 should have added E (the next sorted available after B exhausted)
        assert "E" in summary.all_added

        # Verify iteration 2's added_names are alphabetically before any later candidates
        rec2 = summary.records[1]
        assert rec2.added_names == sorted(rec2.added_names)

    def test_best_record_not_final_iteration(self, tmp_path: Path):
        """Best record is correctly identified even when it is not the final iteration."""
        # Pool: A-G (7 entries). Panel size 4. Each iteration the last panel entry is
        # returned as weak (0.5%) so it gets exhausted and a fresh candidate fills the slot.
        # Distance peaks low at iteration 2 → best should be iteration 2, not the last.
        distances_seq = [0.08, 0.02, 0.06, 0.07]
        call_idx = [0]
        def runner(panel_text, target_text):
            d = distances_seq[call_idx[0] % len(distances_seq)]
            call_idx[0] += 1
            names = [line.split(",")[0] for line in panel_text.strip().splitlines()]
            pops = [(names[0], 60.0), (names[1], 25.0), (names[2], 14.0)]
            if len(names) >= 4:
                pops.append((names[3], 0.5))   # last entry always weak → exhausted each iter
            return _html_for(d, pops)

        pool = _make_pool(["A", "B", "C", "D", "E", "F", "G"])
        summary = run_iterations("T,0.1", pool, self.cfg, runner, tmp_path)

        # Should run multiple iterations; best should be iteration 2 (distance 0.02)
        assert summary.total_iterations >= 2
        assert summary.best_record.result.distance == 0.02
        assert summary.best_record.iteration == 2
        assert summary.best_record.iteration != summary.total_iterations

        # best_result.json should reflect iteration 2
        best_data = json.loads((tmp_path / "best_result.json").read_text())
        assert best_data["iteration"] == 2
        assert abs(best_data["distance"] - 0.02) < 1e-9

    def test_summary_exhausted_count_and_final_panel_size(self, tmp_path: Path):
        """IterationSummary.exhausted_count and final_panel_size are correct."""
        call_idx = [0]
        def runner(panel_text, target_text):
            call_idx[0] += 1
            if call_idx[0] == 1:
                # D is weak -> goes to exhausted_set
                return _html_for(0.05, [("A", 60.0), ("B", 30.0), ("C", 9.0), ("D", 0.5)])
            return _html_for(0.05, [("A", 60.0), ("B", 30.0), ("C", 9.0)])

        pool = _make_pool(["A", "B", "C", "D"])
        summary = run_iterations("T,0.1", pool, self.cfg, runner, tmp_path)

        assert summary.exhausted_count >= 1   # D was exhausted
        assert summary.final_panel_size == summary.records[-1].panel_size


# ---------------------------------------------------------------------------
# Streak-based stop conditions (integration via run_iterations)
# ---------------------------------------------------------------------------

class TestStreakStopConditions:
    """Integration tests: streak counters fire the correct stop inside run_iterations."""

    def _pool(self) -> pd.DataFrame:
        return _make_pool(["A", "B", "C", "D", "E", "F", "G", "H"])

    def test_no_improvement_streak_stops_run(self, tmp_path: Path):
        """Run stops after best distance stalls for stop_if_no_improvement_iterations."""
        cfg = _make_config(
            max_iterations=20,
            stop_distance=0.001,
            remove_percent_below=1.0,
            strong_percent_at_or_above=50.0,
            max_sources_per_panel=4,
            max_initial_panel_size=4,
            stop_if_no_improvement_iterations=3,
        )
        # Distance improves once (iter 1→2), then flatlines — streak should reach 3 and stop
        distances = [0.08, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05]
        call_idx = [0]
        def runner(panel_text, target_text):
            d = distances[min(call_idx[0], len(distances) - 1)]
            call_idx[0] += 1
            return _html_for(d, [("A", 60.0), ("B", 40.0)])

        summary = run_iterations("T,0.1", self._pool(), cfg, runner, tmp_path)
        assert "no_improvement_streak" in summary.stop_reason
        assert summary.total_iterations < 20

    def test_panel_repeat_streak_stops_run(self, tmp_path: Path):
        """Run stops when the effective contributing panel is unchanged for N iterations."""
        cfg = _make_config(
            max_iterations=20,
            stop_distance=0.001,
            remove_percent_below=1.0,
            strong_percent_at_or_above=50.0,
            max_sources_per_panel=4,
            max_initial_panel_size=4,
            stop_if_panel_repeats=2,
        )
        # Always return the same two populations — panel set never changes
        def runner(panel_text, target_text):
            return _html_for(0.05, [("A", 60.0), ("B", 40.0)])

        summary = run_iterations("T,0.1", self._pool(), cfg, runner, tmp_path)
        assert "panel_repeat_streak" in summary.stop_reason
        assert summary.total_iterations < 20

    def test_zero_new_candidates_streak_stops_run(self, tmp_path: Path):
        """Run stops when newly added fill candidates contribute 0% for N iterations."""
        cfg = _make_config(
            max_iterations=20,
            stop_distance=0.001,
            remove_percent_below=1.0,
            strong_percent_at_or_above=50.0,
            max_sources_per_panel=4,
            max_initial_panel_size=4,
            stop_if_all_new_candidates_zero=2,
        )
        # Engine always returns only A and B regardless of what's in the panel.
        # Any fill candidates added (C, D, E, ...) will never appear in results.
        def runner(panel_text, target_text):
            return _html_for(0.05, [("A", 60.0), ("B", 40.0)])

        pool = _make_pool(["A", "B", "C", "D", "E", "F", "G", "H"])
        summary = run_iterations("T,0.1", pool, cfg, runner, tmp_path)
        assert "zero_new_candidates_streak" in summary.stop_reason
        assert summary.total_iterations < 20

    def test_streak_stops_respected_in_stop_reason(self, tmp_path: Path):
        """stop_reason in run_summary.json matches the streak that fired."""
        cfg = _make_config(
            max_iterations=20,
            stop_distance=0.001,
            remove_percent_below=1.0,
            strong_percent_at_or_above=50.0,
            max_sources_per_panel=4,
            max_initial_panel_size=4,
            stop_if_panel_repeats=2,
        )
        def runner(panel_text, target_text):
            return _html_for(0.05, [("A", 60.0), ("B", 40.0)])

        summary = run_iterations("T,0.1", self._pool(), cfg, runner, tmp_path)
        run_summary = json.loads((tmp_path / "run_summary.json").read_text())
        assert run_summary["stop_reason"] == summary.stop_reason
        assert "panel_repeat_streak" in run_summary["stop_reason"]
