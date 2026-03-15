"""tests/test_preselection.py — unit tests for optimizer/preselection.py."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from optimizer.preselection import parse_target_coords, rank_candidates_by_distance
from optimizer.panel_mutation import build_initial_panel_df, MutationState, apply_mutation
from optimizer.scoring import OptimizationConfig
from optimizer.iteration_manager import run_iterations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool_coords(names: list[str], coords: list[list[float]]) -> pd.DataFrame:
    """Build a pool DataFrame from explicit coordinate vectors."""
    dims = {f"dim_{i}": [c[i - 1] for c in coords] for i in range(1, 26)}
    return pd.DataFrame({"name": names, **dims})


def _uniform_pool(names: list[str], base_val: float = 1.0) -> pd.DataFrame:
    """Build a pool where every dimension of every population is base_val."""
    dims = {f"dim_{i}": [base_val] * len(names) for i in range(1, 26)}
    return pd.DataFrame({"name": names, **dims})


def _target_coords(val: float = 0.0) -> np.ndarray:
    """Target at the origin (or uniform val)."""
    return np.full(25, val, dtype=float)


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


def _simple_pool() -> pd.DataFrame:
    dims = {f"dim_{i}": [float(i)] * 4 for i in range(1, 26)}
    return pd.DataFrame({"name": ["A", "B", "C", "D"], **dims})


def _make_config(**overrides) -> OptimizationConfig:
    defaults = dict(
        max_iterations=10,
        stop_distance=0.001,
        remove_percent_below=1.0,
        strong_percent_at_or_above=50.0,
        max_sources_per_panel=4,
        max_initial_panel_size=4,
        initial_panel_strategy="nearest_by_distance",
        nearest_seed_count=4,
    )
    defaults.update(overrides)
    return OptimizationConfig(**defaults)


# ---------------------------------------------------------------------------
# parse_target_coords
# ---------------------------------------------------------------------------

class TestParseTargetCoords:
    def test_correct_shape(self):
        coords = ",".join(["0.1"] * 25)
        result = parse_target_coords(f"PopName,{coords}")
        assert result.shape == (25,)

    def test_correct_values(self):
        vals = [float(i) * 0.01 for i in range(1, 26)]
        coords_str = ",".join(str(v) for v in vals)
        result = parse_target_coords(f"TestPop,{coords_str}")
        np.testing.assert_allclose(result, vals)

    def test_rejects_wrong_field_count(self):
        with pytest.raises(ValueError, match="26 comma-separated fields"):
            parse_target_coords("OnlyName,1.0,2.0")

    def test_name_is_ignored(self):
        a = parse_target_coords("PopA," + ",".join(["0.5"] * 25))
        b = parse_target_coords("PopB," + ",".join(["0.5"] * 25))
        np.testing.assert_array_equal(a, b)


# ---------------------------------------------------------------------------
# rank_candidates_by_distance
# ---------------------------------------------------------------------------

class TestRankCandidatesByDistance:
    def test_nearest_first(self):
        """Closest population by Euclidean distance ranks first."""
        # Target at origin; Pop_near all zeros, Pop_far all ones
        near_coords = [[0.0] * 25]
        far_coords = [[1.0] * 25]
        pool = _make_pool_coords(["Pop_far", "Pop_near"], far_coords + near_coords)
        target = _target_coords(0.0)
        ranked = rank_candidates_by_distance(target, pool)
        assert ranked.iloc[0]["name"] == "Pop_near"
        assert ranked.iloc[1]["name"] == "Pop_far"

    def test_distance_column_present(self):
        pool = _uniform_pool(["A", "B"])
        ranked = rank_candidates_by_distance(_target_coords(0.0), pool)
        assert "euclidean_distance" in ranked.columns

    def test_distance_values_correct(self):
        """sqrt(25 * 1^2) = 5.0 for a unit-offset in all 25 dims."""
        pool = _uniform_pool(["A"], 1.0)
        target = _target_coords(0.0)
        ranked = rank_candidates_by_distance(target, pool)
        assert abs(ranked.iloc[0]["euclidean_distance"] - 5.0) < 1e-9

    def test_zero_distance_for_identical(self):
        pool = _uniform_pool(["A"], 0.5)
        target = np.full(25, 0.5)
        ranked = rank_candidates_by_distance(target, pool)
        assert ranked.iloc[0]["euclidean_distance"] == pytest.approx(0.0)

    def test_tie_broken_by_name(self):
        """Equal-distance candidates are sorted alphabetically by name."""
        # All populations equidistant from origin (unit coords in one dim each)
        coords = [[1.0 if j == i else 0.0 for j in range(25)] for i in range(3)]
        pool = _make_pool_coords(["Zebra", "Apple", "Mango"], coords)
        target = _target_coords(0.0)
        ranked = rank_candidates_by_distance(target, pool)
        assert ranked["name"].tolist() == ["Apple", "Mango", "Zebra"]

    def test_all_distances_non_negative(self):
        pool = _uniform_pool(["A", "B", "C"], 0.3)
        ranked = rank_candidates_by_distance(_target_coords(0.1), pool)
        assert (ranked["euclidean_distance"] >= 0).all()

    def test_row_count_preserved(self):
        pool = _uniform_pool(["A", "B", "C", "D", "E"])
        ranked = rank_candidates_by_distance(_target_coords(), pool)
        assert len(ranked) == 5

    def test_original_pool_not_mutated(self):
        pool = _uniform_pool(["A", "B"])
        original_order = pool["name"].tolist()
        rank_candidates_by_distance(_target_coords(), pool)
        assert pool["name"].tolist() == original_order

    def test_deterministic_repeated_calls(self):
        """Same inputs always produce same ranked output."""
        pool = _uniform_pool(["C", "A", "B"], 0.5)
        target = np.array([float(i) * 0.02 for i in range(25)])
        r1 = rank_candidates_by_distance(target, pool)
        r2 = rank_candidates_by_distance(target, pool)
        pd.testing.assert_frame_equal(r1.reset_index(drop=True),
                                       r2.reset_index(drop=True))


# ---------------------------------------------------------------------------
# build_initial_panel_df with nearest_by_distance strategy
# ---------------------------------------------------------------------------

class TestBuildInitialPanelNearest:
    def test_initial_panel_uses_nearest(self):
        """nearest_by_distance strategy picks the N closest, not alphabetical first N."""
        # Near candidates: Zulu_near, Yellow_near (alphabetically last but closest)
        # Far candidates: Apple_far, Banana_far (alphabetically first but furthest)
        near = [[0.01] * 25, [0.02] * 25]
        far  = [[5.0] * 25,  [6.0] * 25]
        pool = _make_pool_coords(
            ["Apple_far", "Banana_far", "Yellow_near", "Zulu_near"],
            [far[0], far[1], near[0], near[1]],
        )
        target = _target_coords(0.0)
        from optimizer.preselection import rank_candidates_by_distance
        ranked = rank_candidates_by_distance(target, pool)
        cfg = _make_config(max_initial_panel_size=2, nearest_seed_count=2)
        panel = build_initial_panel_df(
            ranked.drop(columns=["euclidean_distance"]), cfg
        )
        names = set(panel["name"].tolist())
        assert "Yellow_near" in names
        assert "Zulu_near" in names
        assert "Apple_far" not in names
        assert "Banana_far" not in names

    def test_alphabetical_strategy_still_works(self):
        """alphabetical strategy picks first N by name as before."""
        pool = _uniform_pool(["Zulu", "Apple", "Mango", "Banana"])
        cfg = _make_config(
            max_initial_panel_size=2,
            nearest_seed_count=2,
            initial_panel_strategy="alphabetical",
        )
        panel = build_initial_panel_df(pool, cfg)
        assert set(panel["name"].tolist()) == {"Apple", "Banana"}

    def test_cap_respected_nearest(self):
        pool = _uniform_pool(["A", "B", "C", "D", "E"])
        cfg = _make_config(max_initial_panel_size=3, nearest_seed_count=3)
        from optimizer.preselection import rank_candidates_by_distance
        ranked = rank_candidates_by_distance(_target_coords(), pool)
        panel = build_initial_panel_df(ranked.drop(columns=["euclidean_distance"]), cfg)
        assert len(panel) == 3


# ---------------------------------------------------------------------------
# Refill uses nearest remaining candidates
# ---------------------------------------------------------------------------

class TestRefillUsesNearest:
    def test_refill_picks_nearest_not_alphabetical(self):
        """After exhausting a weak candidate, refill picks nearest remaining."""
        # Target at origin. Candidates in pool:
        #   A: distance 0.1 (keep, strong)
        #   B: distance 0.5 (weak, removed)
        #   C: distance 0.2 (nearest available for refill)
        #   D: distance 10.0 (far)
        coords_A = [0.1 / 5] * 25       # distance 0.1 from origin
        coords_B = [0.5 / 5] * 25       # distance 0.5
        coords_C = [0.2 / 5] * 25       # distance 0.2
        coords_D = [10.0 / 5] * 25      # distance 10.0
        pool = _make_pool_coords(["A", "B", "C", "D"],
                                  [coords_A, coords_B, coords_C, coords_D])
        target = _target_coords(0.0)
        from optimizer.preselection import rank_candidates_by_distance
        ranked = rank_candidates_by_distance(target, pool)

        # State initialized with distance-ranked names: A(0.1), C(0.2), B(0.5), D(10)
        state = MutationState(candidate_pool_names=ranked["name"].tolist())
        # Mark B as weak (exhausted)
        from optimizer.scoring import PanelClassification
        cl = PanelClassification(strong=["A"], surviving=[], weak=["B"])
        # max_sources_per_panel=2: keep=1 (A), 1 fill slot → only nearest fills
        cfg = _make_config(max_sources_per_panel=2, nearest_seed_count=2)
        mut = apply_mutation(cl, state, pool, cfg)
        # Only 1 fill slot — must choose C (nearest remaining after A and B)
        assert mut.added_names == ["C"]

    def test_refill_deterministic_with_distance_state(self, tmp_path: Path):
        """Two identical runs with nearest_by_distance produce same refill order."""
        pool_names = ["E", "D", "C", "B", "A"]  # intentionally reverse alpha
        # A is closest to origin, E is farthest
        coords = [
            [1.0 / 5] * 25,   # E
            [0.8 / 5] * 25,   # D
            [0.6 / 5] * 25,   # C
            [0.4 / 5] * 25,   # B
            [0.2 / 5] * 25,   # A (closest)
        ]
        pool = _make_pool_coords(pool_names, coords)
        cfg = _make_config(
            max_iterations=5,
            max_sources_per_panel=3,
            nearest_seed_count=2,
            stop_if_panel_repeats=0,
            stop_if_all_new_candidates_zero=0,
            stop_if_no_improvement_iterations=0,
        )
        target_text = "T," + ",".join(["0.0"] * 25)

        def runner(panel_text, target_text):
            names = [ln.split(",")[0] for ln in panel_text.strip().splitlines()]
            pops = [(names[0], 60.0)] + [(n, 0.5) for n in names[1:]]
            return _html_for(0.05, pops)

        s1 = run_iterations(target_text, pool, cfg, runner, tmp_path / "run1")
        s2 = run_iterations(target_text, pool, cfg, runner, tmp_path / "run2")
        assert s1.all_added == s2.all_added
        assert s1.all_removed == s2.all_removed


# ---------------------------------------------------------------------------
# Preselection artifact written to run directory
# ---------------------------------------------------------------------------

class TestPreselectionArtifact:
    def test_preselection_csv_written(self, tmp_path: Path):
        """preselection.csv is created when strategy=nearest_by_distance."""
        pool_names = ["A", "B", "C", "D"]
        dims = {f"dim_{i}": [float(i)] * 4 for i in range(1, 26)}
        pool = pd.DataFrame({"name": pool_names, **dims})
        cfg = _make_config(max_iterations=1, max_sources_per_panel=4, nearest_seed_count=4)
        target_text = "T," + ",".join(["0.0"] * 25)

        def runner(panel_text, target_text):
            return _html_for(0.05, [("A", 60.0), ("B", 40.0)])

        run_iterations(target_text, pool, cfg, runner, tmp_path)
        assert (tmp_path / "preselection.csv").exists()

    def test_preselection_csv_has_expected_columns(self, tmp_path: Path):
        pool_names = ["A", "B", "C"]
        dims = {f"dim_{i}": [float(i)] * 3 for i in range(1, 26)}
        pool = pd.DataFrame({"name": pool_names, **dims})
        cfg = _make_config(max_iterations=1, max_sources_per_panel=3, nearest_seed_count=3)
        target_text = "T," + ",".join(["0.0"] * 25)

        def runner(panel_text, target_text):
            return _html_for(0.05, [("A", 100.0)])

        run_iterations(target_text, pool, cfg, runner, tmp_path)
        df = pd.read_csv(tmp_path / "preselection.csv")
        assert list(df.columns) == ["rank", "name", "euclidean_distance"]
        assert len(df) == 3

    def test_preselection_csv_sorted_by_distance(self, tmp_path: Path):
        """Rows in preselection.csv are in ascending distance order."""
        near_coords = [[0.01] * 25]
        far_coords = [[5.0] * 25]
        pool = _make_pool_coords(["Far", "Near"], far_coords + near_coords)
        cfg = _make_config(max_iterations=1, max_sources_per_panel=2, nearest_seed_count=2)
        target_text = "T," + ",".join(["0.0"] * 25)

        def runner(panel_text, target_text):
            return _html_for(0.05, [("Near", 60.0), ("Far", 40.0)])

        run_iterations(target_text, pool, cfg, runner, tmp_path)
        df = pd.read_csv(tmp_path / "preselection.csv")
        assert df.iloc[0]["name"] == "Near"
        assert df.iloc[1]["name"] == "Far"
        assert df.iloc[0]["euclidean_distance"] < df.iloc[1]["euclidean_distance"]

    def test_no_preselection_csv_for_alphabetical(self, tmp_path: Path):
        """preselection.csv is NOT written when strategy=alphabetical."""
        pool_names = ["A", "B", "C"]
        dims = {f"dim_{i}": [float(i)] * 3 for i in range(1, 26)}
        pool = pd.DataFrame({"name": pool_names, **dims})
        cfg = _make_config(
            max_iterations=1,
            max_sources_per_panel=3,
            nearest_seed_count=3,
            initial_panel_strategy="alphabetical",
        )
        target_text = "T," + ",".join(["0.0"] * 25)

        def runner(panel_text, target_text):
            return _html_for(0.05, [("A", 100.0)])

        run_iterations(target_text, pool, cfg, runner, tmp_path)
        assert not (tmp_path / "preselection.csv").exists()
