"""
optimizer/iteration_manager.py — deterministic iterative optimization loop.

Drives the full iteration sequence:
  initial panel → run engine → classify → mutate → repeat until stop condition.

All decisions are rule-based and reproducible. No LLM, no randomness.

Diagnostics written per-run:
  iteration_NN_panel.txt
  iteration_NN_raw_output.txt
  iteration_NN_result.json       (includes per-iteration summary fields)
  run_summary.json               (aggregate view across all iterations)
  best_result.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pandas as pd

from engine.result_parser import RunResult
from optimizer.panel_mutation import (
    MutationResult,
    MutationState,
    apply_mutation,
    build_initial_panel_df,
    panel_df_to_text,
)
from optimizer.preselection import parse_target_coords, rank_candidates_by_distance
from optimizer.scoring import (
    OptimizationConfig,
    PanelClassification,
    classify_result,
    should_stop,
)


# ---------------------------------------------------------------------------
# Per-iteration record
# ---------------------------------------------------------------------------

@dataclass
class IterationRecord:
    """Complete record of one iteration, including diagnostics."""
    iteration: int                 # 1-based
    panel_text: str                # panel string passed to engine
    panel_size: int                # number of populations in panel_text
    raw_output: str                # raw HTML returned by engine
    result: RunResult              # parsed result
    classification: PanelClassification
    # Diagnostics
    strong_count: int
    surviving_count: int
    weak_count: int
    removed_names: list[str]       # populations dropped this iteration
    added_names: list[str]         # new fill candidates introduced this iteration
    stop_reason: str = ""          # non-empty if this was the final iteration


# ---------------------------------------------------------------------------
# Run-level summary
# ---------------------------------------------------------------------------

@dataclass
class IterationSummary:
    """Complete output of run_iterations()."""
    records: list[IterationRecord]
    best_record: IterationRecord      # record with lowest distance
    stop_reason: str
    total_iterations: int
    all_removed: list[str]            # all populations ever removed, in removal order
    all_added: list[str]              # all populations ever added as fill, in order
    final_panel_size: int
    exhausted_count: int              # size of exhausted_set at end of run


# ---------------------------------------------------------------------------
# Engine runner protocol
# ---------------------------------------------------------------------------

class EngineRunner(Protocol):
    """Callable that takes (panel_text, target_text) -> raw HTML string."""
    def __call__(self, panel_text: str, target_text: str) -> str: ...


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_iterations(
    target_text: str,
    candidate_pool_df: pd.DataFrame,
    config: OptimizationConfig,
    engine_runner: EngineRunner,
    artifact_dir: Path | None = None,
) -> IterationSummary:
    """
    Run the deterministic iterative optimization loop.

    Parameters
    ----------
    target_text:
        G25 target string (single population, panel format).
    candidate_pool_df:
        Full candidate pool DataFrame (region-filtered + period-bucketed).
        Must have columns: name, dim_1 .. dim_25.
    config:
        Optimization configuration.
    engine_runner:
        Callable (panel_text, target_text) -> raw_html. Injected by the
        pipeline so iteration_manager stays decoupled from Playwright.
    artifact_dir:
        If provided, write per-iteration artifacts and run_summary.json here.

    Returns
    -------
    IterationSummary
    """
    # ── Initial setup ──────────────────────────────────────────────────────
    seed_count = config.nearest_seed_count or config.max_initial_panel_size
    strategy = config.initial_panel_strategy

    if strategy == "nearest_by_distance":
        target_coords = parse_target_coords(target_text)
        ranked_pool = rank_candidates_by_distance(target_coords, candidate_pool_df)
        # Write preselection artifact before iteration 1
        if artifact_dir is not None:
            _write_preselection_artifact(artifact_dir, ranked_pool)
        # State uses distance-ranked order for deterministic refill
        state = MutationState(
            candidate_pool_names=ranked_pool["name"].tolist(),
        )
        # Strip the distance column before passing to panel builder
        pool_for_panel = ranked_pool.drop(columns=["euclidean_distance"], errors="ignore")
        current_panel_df = build_initial_panel_df(pool_for_panel, config)

    elif strategy == "stratified_macro":
        from optimizer.seed_strategy import build_stratified_macro_pool
        target_coords = parse_target_coords(target_text)
        strategy_pool = build_stratified_macro_pool(candidate_pool_df, target_coords)
        # Rank strategy pool by distance for deterministic refill ordering
        ranked_strategy = rank_candidates_by_distance(target_coords, strategy_pool)
        if artifact_dir is not None:
            _write_preselection_artifact(artifact_dir, ranked_strategy)
        # Candidate set is limited to the stratified pool; all pops seeded
        state = MutationState(
            candidate_pool_names=ranked_strategy["name"].tolist(),
        )
        current_panel_df = strategy_pool

    else:
        # alphabetical (default/legacy)
        state = MutationState(
            candidate_pool_names=sorted(candidate_pool_df["name"].tolist()),
        )
        current_panel_df = build_initial_panel_df(candidate_pool_df, config)

    effective_pool_size = len(state.candidate_pool_names)
    print(
        f"[iteration_manager] Starting with {len(current_panel_df)} populations "
        f"(pool={effective_pool_size}, "
        f"strategy={strategy}, "
        f"seed_cap={seed_count}, "
        f"max_panel={config.max_sources_per_panel})"
    )

    records: list[IterationRecord] = []
    best_record: IterationRecord | None = None
    stop_reason = ""
    # Track insertion order for all_removed / all_added across iterations
    all_removed: list[str] = []
    all_added: list[str] = []

    # Streak counters for new stop conditions
    _best_distance_seen: float = float("inf")
    no_improvement_streak: int = 0
    panel_repeat_streak: int = 0
    zero_new_candidates_streak: int = 0
    _prev_effective_panel: frozenset[str] = frozenset()
    _prev_added_names: list[str] = []

    # ── Iteration loop ─────────────────────────────────────────────────────
    for iteration in range(1, config.max_iterations + 1):
        panel_text = panel_df_to_text(current_panel_df)
        panel_size = len(current_panel_df)

        print(
            f"[iteration_manager] Iteration {iteration}/{config.max_iterations} "
            f"— panel size: {panel_size}"
        )

        # Run engine
        raw_output = engine_runner(panel_text, target_text)

        # Parse result
        from engine.result_parser import parse_result
        result = parse_result(raw_output)
        print(
            f"[iteration_manager]   distance={result.distance:.8f}, "
            f"populations={len(result.populations)}"
        )

        # ── Update streak counters ──────────────────────────────────────────
        # 1. No-improvement streak
        if result.distance < _best_distance_seen:
            _best_distance_seen = result.distance
            no_improvement_streak = 0
        else:
            no_improvement_streak += 1

        # 2. Panel-repeat streak (skip iteration 1 — no previous panel yet)
        effective_panel: frozenset[str] = frozenset(p.name for p in result.populations)
        if iteration > 1 and effective_panel == _prev_effective_panel:
            panel_repeat_streak += 1
        else:
            panel_repeat_streak = 0
        _prev_effective_panel = effective_panel

        # 3. Zero-new-candidates streak
        result_names = {p.name for p in result.populations}
        if _prev_added_names and not any(n in result_names for n in _prev_added_names):
            zero_new_candidates_streak += 1
        else:
            zero_new_candidates_streak = 0

        # Classify populations
        classification = classify_result(result, config)
        print(
            f"[iteration_manager]   strong={len(classification.strong)}, "
            f"surviving={len(classification.surviving)}, "
            f"weak={len(classification.weak)}"
        )

        # Check distance-based stop before mutating
        stop, reason = should_stop(result, iteration, config)

        # Produce next panel (needed for convergence check even if stopping)
        mutation: MutationResult = apply_mutation(
            classification, state, candidate_pool_df, config
        )

        # Track run-level removed/added lists (insertion order, no deduplication)
        all_removed.extend(mutation.removed_names)
        all_added.extend(mutation.added_names)

        pool_exhausted = state.is_pool_exhausted(set(current_panel_df["name"].tolist()))

        # Recheck stop with convergence + pool + streak info
        if not stop:
            stop, reason = should_stop(
                result, iteration, config,
                panel_unchanged=mutation.panel_unchanged,
                pool_exhausted=pool_exhausted,
                no_improvement_streak=no_improvement_streak,
                panel_repeat_streak=panel_repeat_streak,
                zero_new_candidates_streak=zero_new_candidates_streak,
            )

        # Carry added_names forward for next iteration's zero-contribution check
        _prev_added_names = mutation.added_names

        record = IterationRecord(
            iteration=iteration,
            panel_text=panel_text,
            panel_size=panel_size,
            raw_output=raw_output,
            result=result,
            classification=classification,
            strong_count=len(classification.strong),
            surviving_count=len(classification.surviving),
            weak_count=len(classification.weak),
            removed_names=mutation.removed_names,
            added_names=mutation.added_names,
            stop_reason=reason if stop else "",
        )
        records.append(record)

        # Track best
        if best_record is None or result.distance < best_record.result.distance:
            best_record = record

        # Write per-iteration artifacts
        if artifact_dir is not None:
            _write_iteration_artifacts(artifact_dir, record)

        if stop:
            stop_reason = reason
            print(f"[iteration_manager] Stopping: {reason}")
            break

        current_panel_df = mutation.next_panel_df

    assert best_record is not None  # loop runs at least once

    summary = IterationSummary(
        records=records,
        best_record=best_record,
        stop_reason=stop_reason or f"completed {len(records)} iterations",
        total_iterations=len(records),
        all_removed=all_removed,
        all_added=all_added,
        final_panel_size=records[-1].panel_size,
        exhausted_count=len(state.exhausted_set),
    )

    # Write summary artifacts
    if artifact_dir is not None:
        _write_best_artifact(artifact_dir, best_record)
        _write_run_summary(artifact_dir, summary)

    print(
        f"[iteration_manager] Done. Best distance={best_record.result.distance:.8f} "
        f"(iteration {best_record.iteration}). Reason: {summary.stop_reason}"
    )
    return summary


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------

def _write_iteration_artifacts(artifact_dir: Path, record: IterationRecord) -> None:
    """Write panel, raw output, and diagnostic result JSON for one iteration."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"iteration_{record.iteration:02d}"

    (artifact_dir / f"{prefix}_panel.txt").write_text(
        record.panel_text, encoding="utf-8"
    )
    (artifact_dir / f"{prefix}_raw_output.txt").write_text(
        record.raw_output, encoding="utf-8"
    )

    # result.json includes per-iteration summary fields in addition to RunResult data
    iteration_doc = {
        "iteration": record.iteration,
        "panel_size": record.panel_size,
        "distance": record.result.distance,
        "populations": [p.model_dump() for p in record.result.populations],
        "strong_count": record.strong_count,
        "surviving_count": record.surviving_count,
        "weak_count": record.weak_count,
        "removed_names": record.removed_names,
        "added_names": record.added_names,
        "stop_reason": record.stop_reason,
    }
    (artifact_dir / f"{prefix}_result.json").write_text(
        json.dumps(iteration_doc, indent=2), encoding="utf-8"
    )


def _write_best_artifact(artifact_dir: Path, best: IterationRecord) -> None:
    """Write best_result.json and aggregated_result.json for the best iteration."""
    from optimizer.aggregation import aggregate_by_prefix
    payload = {
        "iteration": best.iteration,
        "distance": best.result.distance,
        "populations": [p.model_dump() for p in best.result.populations],
        "panel_text": best.panel_text,
    }
    (artifact_dir / "best_result.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    aggregated = aggregate_by_prefix(best.result)
    top_samples = sorted(best.result.populations, key=lambda p: p.percent, reverse=True)
    agg_payload = {
        "distance": best.result.distance,
        "best_iteration": best.iteration,
        "by_country": [
            {"region": a.region, "percent": a.percent} for a in aggregated
        ],
        "top_samples": [
            {"name": p.name, "percent": p.percent} for p in top_samples
        ],
    }
    (artifact_dir / "aggregated_result.json").write_text(
        json.dumps(agg_payload, indent=2), encoding="utf-8"
    )


def _write_run_summary(artifact_dir: Path, summary: IterationSummary) -> None:
    """
    Write run_summary.json — aggregate view across all iterations.

    Fields:
      distance_by_iteration  list[float]   — distance at each iteration (1-indexed)
      best_distance          float
      best_iteration         int
      stop_reason            str
      total_iterations       int
      exhausted_count        int           — final size of exhausted_set
      final_panel_size       int
      all_removed            list[str]     — all populations ever removed, in removal order
      all_added              list[str]     — all fill candidates ever added, in add order
      iteration_diagnostics  list[dict]    — per-iteration strong/surviving/weak/removed/added
    """
    doc = {
        "distance_by_iteration": [r.result.distance for r in summary.records],
        "best_distance": summary.best_record.result.distance,
        "best_iteration": summary.best_record.iteration,
        "stop_reason": summary.stop_reason,
        "total_iterations": summary.total_iterations,
        "exhausted_count": summary.exhausted_count,
        "final_panel_size": summary.final_panel_size,
        "all_removed": summary.all_removed,
        "all_added": summary.all_added,
        "iteration_diagnostics": [
            {
                "iteration": r.iteration,
                "panel_size": r.panel_size,
                "distance": r.result.distance,
                "strong_count": r.strong_count,
                "surviving_count": r.surviving_count,
                "weak_count": r.weak_count,
                "removed_names": r.removed_names,
                "added_names": r.added_names,
            }
            for r in summary.records
        ],
    }
    (artifact_dir / "run_summary.json").write_text(
        json.dumps(doc, indent=2), encoding="utf-8"
    )


def _write_preselection_artifact(artifact_dir: Path, ranked_pool: "pd.DataFrame") -> None:
    """Write preselection.csv — full candidate ranking by Euclidean distance."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    out = ranked_pool[["name", "euclidean_distance"]].copy()
    out.insert(0, "rank", range(1, len(out) + 1))
    out.to_csv(artifact_dir / "preselection.csv", index=False)
    print(f"[iteration_manager] Preselection: {len(out)} candidates ranked -> preselection.csv")
