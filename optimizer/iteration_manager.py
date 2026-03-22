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
from optimizer.plausibility import (
    compute_composite_score,
    identify_lone_substitutes,
    identify_remedy_exclusions,
)
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
    # Plausibility scoring
    composite_score: float = 0.0   # distance * all penalty factors
    penalties: dict = None         # per-penalty factor dict (set in __post_init__)

    def __post_init__(self) -> None:
        if self.penalties is None:
            self.penalties = {}


# ---------------------------------------------------------------------------
# Run-level summary
# ---------------------------------------------------------------------------

@dataclass
class IterationSummary:
    """Complete output of run_iterations()."""
    records: list[IterationRecord]
    best_record: IterationRecord      # record with lowest composite_score (or distance)
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
        from optimizer.seed_strategy import (
            build_coverage_aware_pool,
            build_stratified_macro_pool,
        )
        target_coords = parse_target_coords(target_text)
        # Prefer metadata-driven coverage-aware pool when config has mappings.
        if config.prefix_to_region:
            strategy_pool = build_coverage_aware_pool(
                candidate_pool_df,
                target_coords,
                config.prefix_to_region,
                config.region_to_macro,
            )
        else:
            print("[seed_strategy] No metadata mappings in config; using legacy keyword strategy.")
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

        # ── Compute composite plausibility score ────────────────────────────
        composite_score, penalties = compute_composite_score(
            result.distance,
            result.populations,
            config.plausibility,
            config.prefix_to_region,
            config.region_to_macro,
        )
        print(
            f"[iteration_manager]   distance={result.distance:.8f}, "
            f"composite={composite_score:.8f}, "
            f"populations={len(result.populations)}"
        )
        if config.plausibility.enabled and composite_score != result.distance:
            print(
                f"[iteration_manager]   penalties: "
                f"drift={penalties['drift_penalty']:.4f}  "
                f"coherence={penalties['coherence_penalty']:.4f}  "
                f"spread={penalties['spread_penalty']:.4f}  "
                f"substitute={penalties['substitute_penalty']:.4f}"
            )

        # ── Remedy pass (drift + high-% lone outliers) ───────────────────────
        # When composite/distance exceeds the trigger ratio, re-run with
        # structurally problematic populations removed from the panel.
        # Accept the remedy result if its composite score is lower.
        # _effective_panel_df tracks which panel to hand to the secondary pass.
        _effective_panel_df = current_panel_df
        if (
            config.plausibility.enabled
            and config.plausibility.remedy_enabled
            and result.distance > 0
        ):
            penalty_ratio = composite_score / result.distance
            if penalty_ratio >= config.plausibility.remedy_trigger_ratio:
                remedy = _run_remedy_pass(
                    current_panel_df,
                    result,
                    composite_score,
                    penalties,
                    config,
                    engine_runner,
                    target_text,
                )
                if remedy is not None:
                    r_result, r_composite, r_penalties, r_panel_df = remedy
                    if r_composite < composite_score:
                        print(
                            f"[plausibility] remedy accepted: "
                            f"composite {composite_score:.8f} -> {r_composite:.8f} "
                            f"(distance {result.distance:.8f} -> {r_result.distance:.8f})"
                        )
                        result = r_result
                        composite_score = r_composite
                        penalties = r_penalties
                        _effective_panel_df = r_panel_df
                    else:
                        print(
                            f"[plausibility] remedy rejected: "
                            f"remedy composite {r_composite:.8f} >= original {composite_score:.8f}"
                        )

        # ── Lone substitute cleanup pass ──────────────────────────────────────
        # Secondary pass: remove sole, low-% macro-region contributors (noise)
        # if the distance degradation stays within tolerance.
        # Uses _effective_panel_df so drift exclusions from pass 1 are preserved.
        # _panel_for_low_component tracks the panel to pass to the tertiary pass.
        _panel_for_low_component = _effective_panel_df
        if (
            config.plausibility.enabled
            and config.plausibility.lone_substitute_enabled
        ):
            lone_sub = _run_lone_substitute_pass(
                _effective_panel_df,
                result,
                composite_score,
                config,
                engine_runner,
                target_text,
            )
            if lone_sub is not None:
                ls_result, ls_composite, ls_penalties, ls_panel_df = lone_sub
                distance_delta = ls_result.distance - result.distance
                if (
                    ls_composite <= composite_score
                    and distance_delta <= config.plausibility.lone_substitute_distance_tolerance
                ):
                    print(
                        f"[plausibility] lone-sub cleanup accepted: "
                        f"composite {composite_score:.8f} -> {ls_composite:.8f}, "
                        f"distance {result.distance:.8f} -> {ls_result.distance:.8f} "
                        f"(delta={distance_delta:+.8f})"
                    )
                    result = ls_result
                    composite_score = ls_composite
                    penalties = ls_penalties
                    _panel_for_low_component = ls_panel_df
                else:
                    print(
                        f"[plausibility] lone-sub cleanup rejected: "
                        f"composite {ls_composite:.8f} vs {composite_score:.8f}, "
                        f"distance delta={distance_delta:+.8f} "
                        f"(tolerance={config.plausibility.lone_substitute_distance_tolerance})"
                    )

        # ── Low component cleanup pass ─────────────────────────────────────────
        # Tertiary pass: remove residual tiny isolated contributions (<3%) that
        # emerged as new lone-singletons after the lone-sub pass changed the result.
        # Uses _panel_for_low_component (panel from lone-sub pass, or remedy panel)
        # so all prior exclusions are preserved.
        if (
            config.plausibility.enabled
            and config.plausibility.low_component_enabled
        ):
            low_comp = _run_low_component_pass(
                _panel_for_low_component,
                result,
                composite_score,
                config,
                engine_runner,
                target_text,
            )
            if low_comp is not None:
                lc_result, lc_composite, lc_penalties = low_comp
                distance_delta = lc_result.distance - result.distance
                if (
                    lc_composite <= composite_score
                    and distance_delta <= config.plausibility.low_component_distance_tolerance
                ):
                    print(
                        f"[plausibility] low-component cleanup accepted: "
                        f"composite {composite_score:.8f} -> {lc_composite:.8f}, "
                        f"distance {result.distance:.8f} -> {lc_result.distance:.8f} "
                        f"(delta={distance_delta:+.8f})"
                    )
                    result = lc_result
                    composite_score = lc_composite
                    penalties = lc_penalties
                else:
                    print(
                        f"[plausibility] low-component cleanup rejected: "
                        f"composite {lc_composite:.8f} vs {composite_score:.8f}, "
                        f"distance delta={distance_delta:+.8f} "
                        f"(tolerance={config.plausibility.low_component_distance_tolerance})"
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

        # Check plausibility/distance stop before mutating
        stop, reason = should_stop(
            result, iteration, config,
            composite_score=composite_score,
        )

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
                composite_score=composite_score,
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
            composite_score=composite_score,
            penalties=penalties,
        )
        records.append(record)

        # Track best — use composite_score when plausibility is enabled,
        # otherwise fall back to raw distance for backward compatibility.
        if config.plausibility.enabled:
            if best_record is None or composite_score < best_record.composite_score:
                best_record = record
        else:
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
        f"composite={best_record.composite_score:.8f} "
        f"(iteration {best_record.iteration}). Reason: {summary.stop_reason}"
    )
    return summary


# ---------------------------------------------------------------------------
# Remedy pass
# ---------------------------------------------------------------------------

def _run_remedy_pass(
    current_panel_df: "pd.DataFrame",
    result: RunResult,
    composite_score: float,
    penalties: dict,
    config: OptimizationConfig,
    engine_runner: EngineRunner,
    target_text: str,
) -> tuple[RunResult, float, dict] | None:
    """
    Re-run the engine with structurally problematic populations removed.

    Identifies populations from the current result that are driving high
    penalty scores (drift-sensitive overuse, lone-outlier substitutes) and
    removes them from the panel before a second engine run.

    The caller decides whether to accept the remedy result based on whether
    its composite score is lower than the original.

    Parameters
    ----------
    current_panel_df:
        The panel DataFrame used in the current iteration.
    result:
        The parsed engine result for the current iteration.
    composite_score / penalties:
        Already-computed composite score and penalty components.
    config:
        Optimization configuration (carries plausibility settings).
    engine_runner:
        Engine callable (same as used in the main loop).
    target_text:
        G25 target string.

    Returns
    -------
    tuple[RunResult, float, dict, pd.DataFrame] | None
        (remedy_result, remedy_composite_score, remedy_penalties, remedy_panel_df)
        or None if no exclusions were identified or the panel becomes too small.
        The returned panel_df is the filtered panel used for the remedy run —
        pass it to the secondary lone-substitute pass so drift exclusions are preserved.
    """
    to_exclude = identify_remedy_exclusions(
        result.populations,
        config.prefix_to_region,
        config.region_to_macro,
        config.plausibility,
    )

    if not to_exclude:
        return None

    # Build remedy panel: original panel minus excluded populations
    remedy_panel_df = current_panel_df[
        ~current_panel_df["name"].isin(to_exclude)
    ].reset_index(drop=True)

    if len(remedy_panel_df) < 5:
        print("[plausibility] remedy skipped: panel too small after exclusion")
        return None

    print(
        f"[plausibility] remedy pass: excluding {len(to_exclude)} populations "
        f"from {len(current_panel_df)}-pop panel -> {len(remedy_panel_df)} remaining"
    )
    for name in sorted(to_exclude):
        print(f"  [-] {name}")

    remedy_panel_text = panel_df_to_text(remedy_panel_df)
    remedy_raw = engine_runner(remedy_panel_text, target_text)

    from engine.result_parser import parse_result
    remedy_result = parse_result(remedy_raw)

    remedy_composite, remedy_penalties = compute_composite_score(
        remedy_result.distance,
        remedy_result.populations,
        config.plausibility,
        config.prefix_to_region,
        config.region_to_macro,
    )
    print(
        f"[plausibility]   remedy: distance={remedy_result.distance:.8f} "
        f"composite={remedy_composite:.8f} "
        f"(original: distance={result.distance:.8f} composite={composite_score:.8f})"
    )

    return remedy_result, remedy_composite, remedy_penalties, remedy_panel_df


def _run_lone_substitute_pass(
    effective_panel_df: "pd.DataFrame",
    result: RunResult,
    composite_score: float,
    config: OptimizationConfig,
    engine_runner: EngineRunner,
    target_text: str,
) -> tuple[RunResult, float, dict] | None:
    """
    Secondary cleanup pass: remove sole, low-% macro-region contributors.

    Detects populations that are the only representative of their canonical
    macro-region AND whose macro-region total contribution is below
    ``lone_substitute_threshold`` percent.  These are structural noise —
    isolated, minor contributions from a distant macro-region that do not
    meaningfully improve fit distance.

    Uses ``effective_panel_df`` (which may already have drift-sensitive
    populations removed) so that pass-1 exclusions are preserved.

    Parameters
    ----------
    effective_panel_df:
        The panel to further filter.  Typically the remedy-pass panel if
        pass-1 ran, otherwise the original iteration panel.
    result:
        Current best engine result (after any pass-1 acceptance).
    composite_score:
        Current composite score (after any pass-1 acceptance).
    config:
        Optimization configuration.
    engine_runner / target_text:
        Engine callable and target string.

    Returns
    -------
    tuple[RunResult, float, dict, pd.DataFrame] | None
        (ls_result, ls_composite, ls_penalties, ls_panel_df)
        The returned panel_df is the filtered panel used for this run.
        Pass it to the low-component pass so lone-sub exclusions are preserved.
        Caller must apply the distance-tolerance check before accepting.
    """
    if not config.prefix_to_region:
        return None

    to_exclude = identify_lone_substitutes(
        result.populations,
        config.prefix_to_region,
        config.region_to_macro,
        config.plausibility.lone_substitute_threshold,
    )

    if not to_exclude:
        return None

    ls_panel_df = effective_panel_df[
        ~effective_panel_df["name"].isin(to_exclude)
    ].reset_index(drop=True)

    if len(ls_panel_df) < 5:
        print("[plausibility] lone-sub pass skipped: panel too small after exclusion")
        return None

    print(
        f"[plausibility] lone-sub pass: excluding {len(to_exclude)} lone substitutes "
        f"from {len(effective_panel_df)}-pop panel -> {len(ls_panel_df)} remaining"
    )
    for name in sorted(to_exclude):
        # Find the macro-region for logging
        prefix = name.split("_")[0]
        region = config.prefix_to_region.get(prefix, prefix)
        macro = config.region_to_macro.get(region, region)
        pct = next((p.percent for p in result.populations if p.name == name), 0.0)
        print(f"  [-] {name}  ({macro}, {pct:.1f}%)")

    ls_panel_text = panel_df_to_text(ls_panel_df)
    ls_raw = engine_runner(ls_panel_text, target_text)

    from engine.result_parser import parse_result
    ls_result = parse_result(ls_raw)

    ls_composite, ls_penalties = compute_composite_score(
        ls_result.distance,
        ls_result.populations,
        config.plausibility,
        config.prefix_to_region,
        config.region_to_macro,
    )
    print(
        f"[plausibility]   lone-sub: distance={ls_result.distance:.8f} "
        f"composite={ls_composite:.8f} "
        f"(before: distance={result.distance:.8f} composite={composite_score:.8f})"
    )

    return ls_result, ls_composite, ls_penalties, ls_panel_df


def _run_low_component_pass(
    panel_df: "pd.DataFrame",
    result: RunResult,
    composite_score: float,
    config: OptimizationConfig,
    engine_runner: EngineRunner,
    target_text: str,
) -> tuple[RunResult, float, dict] | None:
    """
    Tertiary cleanup pass: remove residual tiny isolated contributions.

    Catches populations below ``low_component_threshold`` (default 3%) that
    are the sole representative of their canonical macro-region.  These
    emerge as new lone-singleton candidates after the lone-substitute pass
    removes other populations and the engine re-assigns their weight.

    Isolation guard (same as lone-sub):
    A population is eligible only if its macro-region appears exactly once
    in the current result.  Populations belonging to a multi-member macro-
    region cluster are kept regardless of their individual percentage.

    Uses ``panel_df`` — the output of the lone-substitute pass (or the
    remedy-pass panel) — so all upstream exclusions are preserved.

    Parameters
    ----------
    panel_df:
        Panel to further filter; should come from the prior pass in the chain.
    result:
        Current best engine result (after any accepted upstream passes).
    composite_score:
        Current composite score.
    config:
        Optimization configuration.
    engine_runner / target_text:
        Engine callable and target string.

    Returns
    -------
    tuple[RunResult, float, dict] | None
        (lc_result, lc_composite, lc_penalties)
        Caller must apply the distance-tolerance check before accepting.
    """
    if not config.prefix_to_region:
        return None

    # Reuse identify_lone_substitutes with the tighter low_component_threshold
    to_exclude = identify_lone_substitutes(
        result.populations,
        config.prefix_to_region,
        config.region_to_macro,
        config.plausibility.low_component_threshold,
    )

    if not to_exclude:
        return None

    lc_panel_df = panel_df[
        ~panel_df["name"].isin(to_exclude)
    ].reset_index(drop=True)

    if len(lc_panel_df) < 5:
        print("[plausibility] low-component pass skipped: panel too small after exclusion")
        return None

    print(
        f"[plausibility] low-component pass: excluding {len(to_exclude)} tiny isolated pops "
        f"from {len(panel_df)}-pop panel -> {len(lc_panel_df)} remaining"
    )
    for name in sorted(to_exclude):
        prefix = name.split("_")[0]
        region = config.prefix_to_region.get(prefix, prefix)
        macro = config.region_to_macro.get(region, region)
        pct = next((p.percent for p in result.populations if p.name == name), 0.0)
        print(f"  [-] {name}  ({macro}, {pct:.1f}%)")

    lc_panel_text = panel_df_to_text(lc_panel_df)
    lc_raw = engine_runner(lc_panel_text, target_text)

    from engine.result_parser import parse_result
    lc_result = parse_result(lc_raw)

    lc_composite, lc_penalties = compute_composite_score(
        lc_result.distance,
        lc_result.populations,
        config.plausibility,
        config.prefix_to_region,
        config.region_to_macro,
    )
    print(
        f"[plausibility]   low-component: distance={lc_result.distance:.8f} "
        f"composite={lc_composite:.8f} "
        f"(before: distance={result.distance:.8f} composite={composite_score:.8f})"
    )

    return lc_result, lc_composite, lc_penalties


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
        "composite_score": record.composite_score,
        "penalties": record.penalties,
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
        "composite_score": best.composite_score,
        "penalties": best.penalties,
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
        "composite_score_by_iteration": [r.composite_score for r in summary.records],
        "best_distance": summary.best_record.result.distance,
        "best_composite_score": summary.best_record.composite_score,
        "best_iteration": summary.best_record.iteration,
        "best_penalties": summary.best_record.penalties,
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
                "composite_score": r.composite_score,
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
