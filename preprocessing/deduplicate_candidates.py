"""
preprocessing/deduplicate_candidates.py — coordinate-based candidate deduplication.

Reduces a candidate pool by clustering near-duplicate populations (same genetic
profile, different sample labels) and keeping one representative per cluster.

Algorithm
---------
1. Compute the full pairwise Euclidean distance matrix over 25 G25 coordinates
   using scipy.spatial.distance.cdist (one vectorised call, no Python loop).
2. Build a threshold graph: undirected edge between i and j if distance < threshold.
3. Find connected components (union-find) — each component is one cluster.
4. Select one representative per cluster by priority:
     a. Closest Euclidean distance to target (if target_coords provided).
     b. Original file order (DataFrame index, ascending).
     c. Name (alphabetical, ascending) as final tiebreaker.

Complexity: O(n² × 25) time, O(n²) memory for the distance matrix.
Acceptable for n ≤ ~5 000.

Artifacts (written when artifact_dir is provided)
---------
  <pool_name>_clusters.csv       — every population mapped to its cluster
  <pool_name>_representatives.csv — representative rows (full G25 data)

Fallback
--------
If deduplication is disabled (config.enabled = False), the original DataFrame
is returned unchanged and no artifacts are written.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class DeduplicationConfig:
    enabled: bool = True
    distance_threshold: float = 0.0015


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DIM_COLUMNS = [f"dim_{i}" for i in range(1, 26)]


def _build_union_find(n: int) -> list[int]:
    return list(range(n))


def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]   # path compression
        i = parent[i]
    return i


def _union(parent: list[int], i: int, j: int) -> None:
    ri, rj = _find(parent, i), _find(parent, j)
    if ri != rj:
        parent[ri] = rj


def _connected_components(dist_matrix: np.ndarray, threshold: float) -> list[int]:
    """
    Return a cluster label array (length n) via union-find on the threshold graph.
    Labels are 0-based integers assigned by first appearance of each root.
    """
    n = dist_matrix.shape[0]
    parent = _build_union_find(n)

    for i in range(n):
        for j in range(i + 1, n):
            if dist_matrix[i, j] < threshold:
                _union(parent, i, j)

    # Normalise roots to consecutive 0-based labels in first-seen order
    root_to_label: dict[int, int] = {}
    labels: list[int] = []
    for i in range(n):
        root = _find(parent, i)
        if root not in root_to_label:
            root_to_label[root] = len(root_to_label)
        labels.append(root_to_label[root])
    return labels


def _choose_representative(
    cluster_indices: list[int],
    pool_df: pd.DataFrame,
    target_coords: np.ndarray | None,
) -> int:
    """
    Return the DataFrame positional index of the best representative.

    Priority:
      1. Minimum Euclidean distance to target (if target_coords provided).
      2. Original file order (positional index in pool_df, ascending).
      3. Name (alphabetical, ascending).
    """
    if len(cluster_indices) == 1:
        return cluster_indices[0]

    candidates = pool_df.iloc[cluster_indices]

    if target_coords is not None:
        coords = candidates[_DIM_COLUMNS].to_numpy(dtype=float)
        diffs = coords - target_coords
        dist_to_target = np.sqrt((diffs ** 2).sum(axis=1))
    else:
        dist_to_target = None

    rows = []
    for rank, idx in enumerate(cluster_indices):
        row = candidates.iloc[rank]
        rows.append((
            dist_to_target[rank] if dist_to_target is not None else 0.0,
            idx,               # positional index = original file order
            row["name"],
            idx,               # carry idx for return value
        ))

    rows.sort(key=lambda t: (t[0], t[1], t[2]))
    return rows[0][3]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deduplicate_candidates(
    pool_df: pd.DataFrame,
    config: DeduplicationConfig,
    target_coords: np.ndarray | None = None,
    artifact_dir: Path | None = None,
    pool_name: str = "pool",
) -> pd.DataFrame:
    """
    Deduplicate a candidate pool by coordinate-similarity clustering.

    Parameters
    ----------
    pool_df:
        Candidate pool DataFrame with columns name, dim_1 .. dim_25.
        Row order is treated as original file order for tiebreaking.
    config:
        Deduplication configuration.
    target_coords:
        Optional 25-element array of target G25 coordinates.
        When provided, representative selection prefers the sample
        closest to the target within each cluster.
    artifact_dir:
        Directory to write cluster artifacts. Skipped if None.
    pool_name:
        Stem used to name artifact files (e.g. "classical_pool").

    Returns
    -------
    pd.DataFrame
        Representative rows only, same columns as pool_df, index reset.
        If config.enabled is False, returns pool_df unchanged.
    """
    if not config.enabled:
        return pool_df

    n = len(pool_df)
    if n == 0:
        return pool_df

    # ── 1. Pairwise distance matrix ────────────────────────────────────────
    coords = pool_df[_DIM_COLUMNS].to_numpy(dtype=float)
    dist_matrix = cdist(coords, coords, metric="euclidean")

    # ── 2. Connected components ────────────────────────────────────────────
    labels = _connected_components(dist_matrix, config.distance_threshold)

    # ── 3. Representative selection ────────────────────────────────────────
    from collections import defaultdict
    clusters: dict[int, list[int]] = defaultdict(list)
    for pos_idx, label in enumerate(labels):
        clusters[label].append(pos_idx)

    rep_positions: set[int] = set()
    for label in sorted(clusters):
        rep_pos = _choose_representative(clusters[label], pool_df, target_coords)
        rep_positions.add(rep_pos)

    # ── 4. Build cluster annotation table ─────────────────────────────────
    # representative name for each position
    rep_name_by_pos: dict[int, str] = {}
    for label in sorted(clusters):
        rep_pos = _choose_representative(clusters[label], pool_df, target_coords)
        rep_name = pool_df.iloc[rep_pos]["name"]
        for pos in clusters[label]:
            rep_name_by_pos[pos] = rep_name

    cluster_rows = []
    for pos_idx in range(n):
        cluster_rows.append({
            "cluster_id": labels[pos_idx],
            "name": pool_df.iloc[pos_idx]["name"],
            "is_representative": pos_idx in rep_positions,
            "representative": rep_name_by_pos[pos_idx],
        })
    cluster_df = pd.DataFrame(cluster_rows)

    # ── 5. Representatives DataFrame ──────────────────────────────────────
    rep_df = pool_df.iloc[sorted(rep_positions)].reset_index(drop=True)

    # ── 6. Write artifacts ─────────────────────────────────────────────────
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        cluster_df.to_csv(
            artifact_dir / f"{pool_name}_clusters.csv", index=False
        )
        rep_df.to_csv(
            artifact_dir / f"{pool_name}_representatives.csv", index=False
        )

    n_clusters = len(set(labels))
    n_singletons = sum(1 for members in clusters.values() if len(members) == 1)
    print(
        f"[deduplication] {n} candidates -> {len(rep_df)} representatives "
        f"({n_clusters} clusters, {n_singletons} singletons, "
        f"threshold={config.distance_threshold})"
    )

    return rep_df
