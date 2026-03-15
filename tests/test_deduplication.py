"""tests/test_deduplication.py — unit tests for preprocessing/deduplicate_candidates.py."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from preprocessing.deduplicate_candidates import (
    DeduplicationConfig,
    deduplicate_candidates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIM_COLS = [f"dim_{i}" for i in range(1, 26)]


def _pool(rows: list[tuple[str, list[float]]]) -> pd.DataFrame:
    """Build a minimal G25 DataFrame from (name, coords) pairs."""
    records = [{"name": name, **{f"dim_{i+1}": v for i, v in enumerate(coords)}}
               for name, coords in rows]
    return pd.DataFrame(records)


def _uniform_coords(val: float) -> list[float]:
    return [val] * 25


def _cfg(enabled: bool = True, threshold: float = 0.0015) -> DeduplicationConfig:
    return DeduplicationConfig(enabled=enabled, distance_threshold=threshold)


# ---------------------------------------------------------------------------
# Disabled — passthrough
# ---------------------------------------------------------------------------

class TestDisabled:
    def test_returns_original_df_unchanged(self):
        pool = _pool([("A_x", _uniform_coords(0.0)), ("B_x", _uniform_coords(0.0))])
        result = deduplicate_candidates(pool, _cfg(enabled=False))
        pd.testing.assert_frame_equal(result, pool)

    def test_no_artifacts_written(self, tmp_path: Path):
        pool = _pool([("A_x", _uniform_coords(0.0)), ("B_x", _uniform_coords(0.0))])
        deduplicate_candidates(pool, _cfg(enabled=False), artifact_dir=tmp_path, pool_name="test")
        assert list(tmp_path.iterdir()) == []

    def test_empty_pool_disabled(self):
        pool = _pool([])
        result = deduplicate_candidates(pool, _cfg(enabled=False))
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Threshold behaviour
# ---------------------------------------------------------------------------

class TestThresholdBehaviour:
    def test_identical_coords_cluster_together(self):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(0.0)),
            ("C_x", _uniform_coords(0.0)),
        ])
        result = deduplicate_candidates(pool, _cfg(threshold=0.0015))
        assert len(result) == 1

    def test_distant_coords_stay_separate(self):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(1.0)),
        ])
        result = deduplicate_candidates(pool, _cfg(threshold=0.0015))
        assert len(result) == 2

    def test_just_below_threshold_merges(self):
        # distance = sqrt(25 * delta²) — set delta so distance < threshold
        threshold = 0.01
        delta = (threshold - 1e-9) / (25 ** 0.5)
        pool = _pool([
            ("A_x", [0.0] * 25),
            ("B_x", [delta] * 25),
        ])
        result = deduplicate_candidates(pool, _cfg(threshold=threshold))
        assert len(result) == 1

    def test_just_above_threshold_stays_separate(self):
        threshold = 0.01
        delta = (threshold + 1e-6) / (25 ** 0.5)
        pool = _pool([
            ("A_x", [0.0] * 25),
            ("B_x", [delta] * 25),
        ])
        result = deduplicate_candidates(pool, _cfg(threshold=threshold))
        assert len(result) == 2

    def test_singleton_populations_all_kept(self):
        """Populations that don't cluster with anyone are all kept."""
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(1.0)),
            ("C_x", _uniform_coords(2.0)),
        ])
        result = deduplicate_candidates(pool, _cfg(threshold=0.0015))
        assert len(result) == 3

    def test_mixed_cluster_sizes(self):
        """Two populations cluster; one stays singleton."""
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(0.0)),   # same as A -> cluster
            ("C_x", _uniform_coords(1.0)),   # distant -> singleton
        ])
        result = deduplicate_candidates(pool, _cfg(threshold=0.0015))
        assert len(result) == 2

    def test_empty_pool_enabled(self):
        pool = _pool([])
        result = deduplicate_candidates(pool, _cfg())
        assert len(result) == 0

    def test_single_population_kept(self):
        pool = _pool([("A_x", _uniform_coords(0.5))])
        result = deduplicate_candidates(pool, _cfg())
        assert len(result) == 1
        assert result.iloc[0]["name"] == "A_x"


# ---------------------------------------------------------------------------
# Representative selection — no target
# ---------------------------------------------------------------------------

class TestRepresentativeSelectionNoTarget:
    def test_file_order_tiebreak(self):
        """Without a target, file order determines representative (first row wins)."""
        pool = _pool([
            ("B_x", _uniform_coords(0.0)),
            ("A_x", _uniform_coords(0.0)),
        ])
        result = deduplicate_candidates(pool, _cfg())
        assert result.iloc[0]["name"] == "B_x"   # B is at index 0

    def test_name_tiebreak_when_same_index(self):
        """
        Name is the final tiebreaker. Because pool_df positions are unique,
        this test confirms name ordering doesn't override file order.
        """
        pool = _pool([
            ("Z_x", _uniform_coords(0.0)),   # index 0
            ("A_x", _uniform_coords(0.0)),   # index 1
        ])
        result = deduplicate_candidates(pool, _cfg())
        # File order wins: index 0 (Z_x) is kept
        assert result.iloc[0]["name"] == "Z_x"

    def test_three_way_cluster_first_file_position_kept(self):
        pool = _pool([
            ("Second_x", _uniform_coords(0.0)),
            ("First_x",  _uniform_coords(0.0)),
            ("Third_x",  _uniform_coords(0.0)),
        ])
        result = deduplicate_candidates(pool, _cfg())
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Second_x"   # index 0


# ---------------------------------------------------------------------------
# Representative selection — with target
# ---------------------------------------------------------------------------

class TestRepresentativeSelectionWithTarget:
    def test_closest_to_target_wins(self):
        """When a target is given, the population nearest to it is kept.

        Both populations must be within the threshold of each other (so they
        form one cluster). Near_x is exactly at the target; Far_x is slightly
        offset but still within threshold.
        """
        target = np.array([0.5] * 25)
        # tiny offset so both are within threshold=0.01 of each other
        offset = 0.001 / (25 ** 0.5)   # dist(Near_x, Far_x) = 0.001 < 0.01
        pool = _pool([
            ("Far_x",  [0.5 + offset] * 25),   # slightly away from target
            ("Near_x", [0.5] * 25),             # exactly at target -> dist=0
        ])
        result = deduplicate_candidates(pool, _cfg(threshold=0.01), target_coords=target)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Near_x"

    def test_target_tiebreak_falls_back_to_file_order(self):
        """Equal distance to target -> file order decides."""
        target = np.array([0.5] * 25)
        pool = _pool([
            ("B_x", _uniform_coords(0.0)),   # index 0, same distance as A
            ("A_x", _uniform_coords(1.0)),   # index 1, same distance as B
        ])
        result = deduplicate_candidates(pool, _cfg(threshold=10.0), target_coords=target)
        # Both equidistant from target (distance = sqrt(25*0.25) = 2.5)
        # File order: B_x (index 0) wins
        assert result.iloc[0]["name"] == "B_x"

    def test_target_ignored_when_not_provided(self):
        """Without target_coords, file order is the tiebreaker."""
        pool = _pool([
            ("B_x", _uniform_coords(0.0)),
            ("A_x", _uniform_coords(0.0)),
        ])
        result = deduplicate_candidates(pool, _cfg(), target_coords=None)
        assert result.iloc[0]["name"] == "B_x"   # index 0


# ---------------------------------------------------------------------------
# Determinism — stable repeated runs
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_result_on_repeated_calls(self):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(0.0)),
            ("C_x", _uniform_coords(1.0)),
        ])
        cfg = _cfg()
        r1 = deduplicate_candidates(pool.copy(), cfg)
        r2 = deduplicate_candidates(pool.copy(), cfg)
        pd.testing.assert_frame_equal(r1, r2)

    def test_result_independent_of_numpy_random_state(self):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(0.0)),
        ])
        cfg = _cfg()
        np.random.seed(42)
        r1 = deduplicate_candidates(pool.copy(), cfg)
        np.random.seed(999)
        r2 = deduplicate_candidates(pool.copy(), cfg)
        assert list(r1["name"]) == list(r2["name"])


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------

class TestOutputStructure:
    def test_output_has_same_columns_as_input(self):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(0.1)),
        ])
        result = deduplicate_candidates(pool, _cfg(threshold=10.0))
        assert list(result.columns) == list(pool.columns)

    def test_all_dim_values_preserved(self):
        coords = [float(i) / 100 for i in range(25)]
        pool = _pool([("A_x", coords), ("B_x", _uniform_coords(1.0))])
        result = deduplicate_candidates(pool, _cfg(threshold=0.0015))
        row_a = result[result["name"] == "A_x"]
        assert len(row_a) == 1
        for i, val in enumerate(coords, start=1):
            assert row_a.iloc[0][f"dim_{i}"] == pytest.approx(val)

    def test_index_reset_on_output(self):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(0.0)),
            ("C_x", _uniform_coords(1.0)),
        ])
        result = deduplicate_candidates(pool, _cfg())
        assert list(result.index) == list(range(len(result)))


# ---------------------------------------------------------------------------
# Artifact consistency
# ---------------------------------------------------------------------------

class TestArtifacts:
    def test_clusters_csv_written(self, tmp_path: Path):
        pool = _pool([("A_x", _uniform_coords(0.0)), ("B_x", _uniform_coords(1.0))])
        deduplicate_candidates(pool, _cfg(), artifact_dir=tmp_path, pool_name="test")
        assert (tmp_path / "test_clusters.csv").exists()

    def test_representatives_csv_written(self, tmp_path: Path):
        pool = _pool([("A_x", _uniform_coords(0.0)), ("B_x", _uniform_coords(1.0))])
        deduplicate_candidates(pool, _cfg(), artifact_dir=tmp_path, pool_name="test")
        assert (tmp_path / "test_representatives.csv").exists()

    def test_clusters_csv_has_required_columns(self, tmp_path: Path):
        pool = _pool([("A_x", _uniform_coords(0.0)), ("B_x", _uniform_coords(1.0))])
        deduplicate_candidates(pool, _cfg(), artifact_dir=tmp_path, pool_name="test")
        df = pd.read_csv(tmp_path / "test_clusters.csv")
        for col in ("cluster_id", "name", "is_representative", "representative"):
            assert col in df.columns

    def test_clusters_csv_covers_all_populations(self, tmp_path: Path):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(0.0)),
            ("C_x", _uniform_coords(1.0)),
        ])
        deduplicate_candidates(pool, _cfg(), artifact_dir=tmp_path, pool_name="test")
        df = pd.read_csv(tmp_path / "test_clusters.csv")
        assert len(df) == 3

    def test_every_dropped_sample_links_to_representative(self, tmp_path: Path):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(0.0)),   # B clusters with A; A kept (file order)
        ])
        deduplicate_candidates(pool, _cfg(), artifact_dir=tmp_path, pool_name="test")
        df = pd.read_csv(tmp_path / "test_clusters.csv")
        dropped = df[~df["is_representative"]]
        # Each dropped row must have a non-empty representative name
        assert all(dropped["representative"].notna())
        assert all(dropped["representative"] != "")

    def test_representative_column_matches_kept_name(self, tmp_path: Path):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),   # kept (index 0)
            ("B_x", _uniform_coords(0.0)),   # dropped
        ])
        deduplicate_candidates(pool, _cfg(), artifact_dir=tmp_path, pool_name="test")
        df = pd.read_csv(tmp_path / "test_clusters.csv")
        reps = set(df[df["is_representative"]]["name"])
        for _, row in df[~df["is_representative"]].iterrows():
            assert row["representative"] in reps

    def test_representatives_csv_contains_full_g25_columns(self, tmp_path: Path):
        pool = _pool([("A_x", _uniform_coords(0.0)), ("B_x", _uniform_coords(1.0))])
        deduplicate_candidates(pool, _cfg(), artifact_dir=tmp_path, pool_name="test")
        rep_df = pd.read_csv(tmp_path / "test_representatives.csv")
        assert "name" in rep_df.columns
        for i in range(1, 26):
            assert f"dim_{i}" in rep_df.columns

    def test_representative_count_matches_cluster_count(self, tmp_path: Path):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(0.0)),   # clusters with A
            ("C_x", _uniform_coords(1.0)),   # singleton
        ])
        deduplicate_candidates(pool, _cfg(), artifact_dir=tmp_path, pool_name="test")
        cluster_df = pd.read_csv(tmp_path / "test_clusters.csv")
        rep_df = pd.read_csv(tmp_path / "test_representatives.csv")
        n_reps_in_clusters = cluster_df["is_representative"].sum()
        assert len(rep_df) == n_reps_in_clusters

    def test_artifacts_not_written_when_dir_is_none(self):
        pool = _pool([("A_x", _uniform_coords(0.0)), ("B_x", _uniform_coords(0.0))])
        # Should not raise; no files created
        result = deduplicate_candidates(pool, _cfg(), artifact_dir=None)
        assert len(result) == 1

    def test_clusters_same_id_for_merged_populations(self, tmp_path: Path):
        pool = _pool([
            ("A_x", _uniform_coords(0.0)),
            ("B_x", _uniform_coords(0.0)),   # same cluster as A
            ("C_x", _uniform_coords(1.0)),   # different cluster
        ])
        deduplicate_candidates(pool, _cfg(), artifact_dir=tmp_path, pool_name="test")
        df = pd.read_csv(tmp_path / "test_clusters.csv")
        a_id = df[df["name"] == "A_x"]["cluster_id"].iloc[0]
        b_id = df[df["name"] == "B_x"]["cluster_id"].iloc[0]
        c_id = df[df["name"] == "C_x"]["cluster_id"].iloc[0]
        assert a_id == b_id
        assert a_id != c_id
