"""
orchestration/pipeline.py — end-to-end run orchestration.

Two entry points:

  run_single()      — one Vahaduo run from a pre-built panel file
  run_iterative()   — deterministic iterative optimization from a candidate pool

Interpretation profiles are optional.  Pass an InterpretationConfig loaded via
``load_profile()`` to enable macro-region aggregation and generic summary text.
Without a profile, only sample-level and prefix-level artifacts are written.

Usage
-----
    from pathlib import Path
    from orchestration.pipeline import load_config, load_profile, run_iterative

    config  = load_config(Path("config.yaml"))
    profile = load_profile("eastmed_europe")          # optional

    summary = run_iterative(
        target_file=Path("data/targets/my_target.csv"),
        candidate_pool_file=Path("data/candidate_pools/classical_pool.csv"),
        config=config,
        interpretation=profile,                        # omit for no-profile run
    )
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from engine.local_server import LocalVahaduoServer
from engine.playwright_runner import run_vahaduo
from engine.result_parser import RunResult, parse_result
from engine.setup import clone_or_update_vahaduo
from engine.vahaduo_bridge import VahaduoBridge
from optimizer.aggregation import aggregate_by_prefix
from optimizer.interpretation import InterpretationConfig, build_generic_summary
from optimizer.iteration_manager import IterationSummary, run_iterations
from optimizer.plausibility import PlausibilityConfig
from optimizer.scoring import OptimizationConfig
from preprocessing.loader import load_g25_file


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Full pipeline configuration loaded from config.yaml."""
    engine_path: Path
    engine_repo: str
    port: int
    runs_dir: Path
    optimization: OptimizationConfig
    profiles_dir: Path = field(default_factory=lambda: Path("interpretation_profiles"))
    user_profiles: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


def _load_plausibility_config(pcfg: dict) -> PlausibilityConfig:
    """Build a PlausibilityConfig from the optimization.plausibility yaml sub-section."""
    if not pcfg:
        return PlausibilityConfig()
    return PlausibilityConfig(
        enabled=pcfg.get("enabled", True),
        drift_weight=pcfg.get("drift_weight", 0.30),
        coherence_max_regions=pcfg.get("coherence_max_regions", 5),
        coherence_per_extra_region=pcfg.get("coherence_per_extra_region", 0.10),
        coherence_min_percent=pcfg.get("coherence_min_percent", 3.0),
        spread_dust_threshold=pcfg.get("spread_dust_threshold", 1.0),
        spread_per_dust=pcfg.get("spread_per_dust", 0.02),
        substitute_min_percent=pcfg.get("substitute_min_percent", 5.0),
        substitute_per_outlier=pcfg.get("substitute_per_outlier", 0.10),
        remedy_enabled=pcfg.get("remedy_enabled", True),
        remedy_trigger_ratio=pcfg.get("remedy_trigger_ratio", 1.15),
        remedy_drift_min_percent=pcfg.get("remedy_drift_min_percent", 10.0),
        lone_substitute_enabled=pcfg.get("lone_substitute_enabled", True),
        lone_substitute_threshold=pcfg.get("lone_substitute_threshold", 5.0),
        lone_substitute_distance_tolerance=pcfg.get("lone_substitute_distance_tolerance", 0.001),
        low_component_enabled=pcfg.get("low_component_enabled", True),
        low_component_threshold=pcfg.get("low_component_threshold", 3.0),
        low_component_distance_tolerance=pcfg.get("low_component_distance_tolerance", 0.001),
    )


def load_config(config_path: Path = Path("config.yaml")) -> Config:
    """Load and validate config.yaml into a Config dataclass."""
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    opt = raw.get("optimization", {})
    return Config(
        engine_path=Path(raw["vahaduo"]["engine_path"]),
        engine_repo=raw["vahaduo"]["engine_repo"],
        port=raw["vahaduo"].get("port", 0),
        runs_dir=Path(raw["results"]["runs_dir"]),
        optimization=OptimizationConfig(
            max_iterations=opt.get("max_iterations", 20),
            stop_distance=opt.get("stop_distance", 0.02),
            remove_percent_below=opt.get("remove_percent_below", 1.0),
            strong_percent_at_or_above=opt.get("strong_percent_at_or_above", 10.0),
            max_sources_per_panel=opt.get("max_sources_per_panel", 25),
            max_initial_panel_size=opt.get("max_initial_panel_size", 40),
            stop_if_no_improvement_iterations=opt.get("stop_if_no_improvement_iterations", 0),
            stop_if_panel_repeats=opt.get("stop_if_panel_repeats", 0),
            stop_if_all_new_candidates_zero=opt.get("stop_if_all_new_candidates_zero", 0),
            initial_panel_strategy=opt.get("initial_panel_strategy", "alphabetical"),
            nearest_seed_count=opt.get("nearest_seed_count"),
            # Metadata mappings for coverage-aware seeding
            prefix_to_region=raw.get("interpretation", {}).get("prefix_to_region", {}),
            region_to_macro=raw.get("interpretation", {}).get("region_to_macro", {}),
            # Plausibility constraints
            plausibility=_load_plausibility_config(opt.get("plausibility", {})),
        ),
        profiles_dir=Path(
            raw.get("interpretation_profiles_dir", "interpretation_profiles")
        ),
        user_profiles=raw.get("user_profiles") or {},
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Profile loader
# ---------------------------------------------------------------------------

def load_profile(
    name: str,
    profiles_dir: Path | None = None,
) -> InterpretationConfig:
    """
    Load a named interpretation profile from the profiles directory.

    Parameters
    ----------
    name:
        Profile stem, e.g. ``"eastmed_europe"`` for
        ``interpretation_profiles/eastmed_europe.yaml``.
    profiles_dir:
        Directory to search.  Defaults to ``interpretation_profiles/``
        relative to the current working directory.

    Returns
    -------
    InterpretationConfig

    Raises
    ------
    FileNotFoundError
        If the profile YAML does not exist.
    """
    if profiles_dir is None:
        profiles_dir = Path("interpretation_profiles")
    path = profiles_dir / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Interpretation profile '{name}' not found: {path}\n"
            f"Available profiles: {_list_profiles(profiles_dir)}"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cf = raw.get("candidate_filter") or {}
    return InterpretationConfig(
        prefix_to_region=raw.get("prefix_to_region") or {},
        region_to_macro=raw.get("region_to_macro") or {},
        macro_to_label=raw.get("macro_to_label") or {},
        allowed_macro_regions=cf.get("allowed_macro_regions") or [],
        excluded_super_regions=cf.get("excluded_super_regions") or [],
        excluded_regions=cf.get("excluded_regions") or [],
        profile_label=raw.get("profile_label") or "",
        use_standard_mode=raw.get("use_standard_mode", True),
        apply_plausibility_constraints=raw.get("apply_plausibility_constraints", True),
        apply_remedy_passes=raw.get("apply_remedy_passes", True),
    )


def _list_profiles(profiles_dir: Path) -> list[str]:
    """Return sorted profile names (stems) found in profiles_dir."""
    if not profiles_dir.exists():
        return []
    return sorted(p.stem for p in profiles_dir.glob("*.yaml"))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:20]


def _config_hash(config: Config) -> str:
    blob = json.dumps(config.raw, sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:16]


def _engine_commit(engine_path: Path) -> str:
    meta_path = engine_path / ".clone_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        return meta.get("commit_sha", "unknown")
    return "unknown"


def _ensure_engine(config: Config) -> None:
    if not config.engine_path.exists():
        print("[pipeline] Engine not found — cloning...")
        clone_or_update_vahaduo(config.engine_path)


def _target_text_from_file(target_file: Path) -> str:
    """Load target file and return a single-row G25 string."""
    target_df = load_g25_file(target_file)
    if len(target_df) != 1:
        raise ValueError(
            f"Target file must contain exactly one population row. "
            f"Got {len(target_df)} rows in {target_file}."
        )
    dims = ",".join(str(target_df[f"dim_{i}"].iloc[0]) for i in range(1, 26))
    return f"{target_df['name'].iloc[0]},{dims}"


def _write_single_artifacts(
    run_dir: Path,
    run_id: str,
    config: Config,
    target_file: Path,
    panel_file: Path,
    panel_text: str,
    raw_output: str,
    result: RunResult,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "run_id": run_id,
        "mode": "single",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine_commit": _engine_commit(config.engine_path),
        "config_hash": _config_hash(config),
        "target_file": str(target_file),
        "panel_file": str(panel_file),
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    shutil.copy2(target_file, run_dir / "target_used.csv")
    (run_dir / "panel_used.txt").write_text(panel_text, encoding="utf-8")
    (run_dir / "raw_output.txt").write_text(raw_output, encoding="utf-8")
    (run_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"[pipeline] Artifacts written to {run_dir}")


def _write_iterative_meta(
    run_dir: Path,
    run_id: str,
    config: Config,
    target_file: Path,
    candidate_pool_file: Path,
    summary: IterationSummary,
    interpretation: InterpretationConfig | None,
    profile_name: str | None,
    profile_filter_summary: dict | None = None,
) -> None:
    meta = {
        "run_id": run_id,
        "mode": "iterative",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine_commit": _engine_commit(config.engine_path),
        "config_hash": _config_hash(config),
        "target_file": str(target_file),
        "candidate_pool_file": str(candidate_pool_file),
        "total_iterations": summary.total_iterations,
        "stop_reason": summary.stop_reason,
        "best_iteration": summary.best_record.iteration,
        "best_distance": summary.best_record.result.distance,
        "exhausted_count": summary.exhausted_count,
        "final_panel_size": summary.final_panel_size,
        "profile": profile_name,   # null when no profile was used
        "profile_label": interpretation.profile_label if interpretation else None,
        "profile_filter": profile_filter_summary or {},
        "optimization": {
            "max_iterations": config.optimization.max_iterations,
            "stop_distance": config.optimization.stop_distance,
            "remove_percent_below": config.optimization.remove_percent_below,
            "strong_percent_at_or_above": config.optimization.strong_percent_at_or_above,
            "max_sources_per_panel": config.optimization.max_sources_per_panel,
            "max_initial_panel_size": config.optimization.max_initial_panel_size,
        },
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    shutil.copy2(target_file, run_dir / "target_used.csv")

    # generic_summary.json — written only when an interpretation profile is active
    if interpretation is not None:
        aggregated = aggregate_by_prefix(summary.best_record.result)
        generic = build_generic_summary(
            summary.best_record.result, aggregated, interpretation
        )
        generic_doc = {
            "profile": profile_name,
            "distance": generic.distance,
            "top_samples": generic.top_samples,
            "by_prefix": generic.by_prefix,
            "by_macro_region": [
                {"macro_region": g.macro_region, "percent": g.percent, "label": g.label}
                for g in generic.by_macro_region
            ],
            "summary_lines": generic.summary_lines,
        }
        (run_dir / "generic_summary.json").write_text(
            json.dumps(generic_doc, indent=2), encoding="utf-8"
        )

    print(f"[pipeline] Iterative run artifacts in {run_dir}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_single(
    target_file: Path,
    panel_file: Path,
    config: Config,
) -> RunResult:
    """
    Execute one Vahaduo run from a pre-built panel file.

    Parameters
    ----------
    target_file:
        Path to a G25 CSV/TSV target file (one population row).
    panel_file:
        Path to a pre-built panel text file (from panel_builder.write_panel()).
    config:
        Pipeline configuration.

    Returns
    -------
    RunResult
    """
    _ensure_engine(config)
    target_text = _target_text_from_file(target_file)

    if not panel_file.exists():
        raise FileNotFoundError(f"Panel file not found: {panel_file}")
    panel_text = panel_file.read_text(encoding="utf-8")

    bridge = VahaduoBridge()
    with LocalVahaduoServer(config.engine_path, port=config.port) as url:
        raw_output = run_vahaduo(url, panel_text, target_text, bridge)

    result = parse_result(raw_output)

    run_id = _make_run_id()
    run_dir = config.runs_dir / run_id
    _write_single_artifacts(
        run_dir=run_dir,
        run_id=run_id,
        config=config,
        target_file=target_file,
        panel_file=panel_file,
        panel_text=panel_text,
        raw_output=raw_output,
        result=result,
    )
    return result


def run_iterative(
    target_file: Path,
    candidate_pool_file: Path,
    config: Config,
    interpretation: InterpretationConfig | None = None,
    profile_name: str | None = None,
    artifact_dir: Path | None = None,
) -> IterationSummary:
    """
    Run deterministic iterative optimization from a candidate pool.

    The engine server stays open for the entire run. Each iteration:
      1. Sends the current panel + target to the local Vahaduo engine.
      2. Parses the result.
      3. Classifies populations by threshold.
      4. Mutates the panel deterministically.
      5. Writes per-iteration artifacts.
      6. Checks stop conditions.

    Artifacts always written to the run directory:
      meta.json            (includes "profile": name or null)
      target_used.csv
      preselection.csv     (when nearest_by_distance seeding)
      iteration_NN_panel.txt
      iteration_NN_raw_output.txt
      iteration_NN_result.json
      best_result.json
      aggregated_result.json

    Additional artifact written only when interpretation is provided:
      generic_summary.json

    Parameters
    ----------
    target_file:
        Path to a G25 CSV/TSV target file (one population row).
    candidate_pool_file:
        Path to the candidate pool CSV (from candidate_reducer output).
    config:
        Pipeline configuration.
    interpretation:
        Optional InterpretationConfig loaded via ``load_profile()``.
        When None, macro-region aggregation and generic_summary.json are skipped.
    profile_name:
        Display name recorded in meta.json and generic_summary.json.
        Typically the profile stem (e.g. "eastmed_europe").
    artifact_dir:
        Explicit directory to write all artifacts into.  When provided,
        overrides the auto-generated ``config.runs_dir / <run_id>`` path.
        The caller is responsible for ensuring it is unique across concurrent
        runs.  Used by ``run_dual_mode()`` to place sub-run artifacts inside a
        master directory.

    Returns
    -------
    IterationSummary
        Full record of all iterations and the best result.
    """
    _ensure_engine(config)
    target_text = _target_text_from_file(target_file)

    if not candidate_pool_file.exists():
        raise FileNotFoundError(f"Candidate pool file not found: {candidate_pool_file}")
    candidate_pool_df = load_g25_file(candidate_pool_file)
    if len(candidate_pool_df) == 0:
        raise ValueError(f"Candidate pool is empty: {candidate_pool_file}")

    # ── Profile candidate filter (metadata-driven, applied before optimization) ──
    # Uses canonical_macro_region and broad_super_region columns from
    # sample_metadata.annotate_df() — no substring matching on sample names.
    _profile_filter_summary: dict = {}
    _needs_filter = (
        interpretation is not None
        and (
            interpretation.allowed_macro_regions
            or interpretation.excluded_super_regions
            or interpretation.excluded_regions
        )
    )
    if _needs_filter:
        import pandas as _pd
        from preprocessing.sample_metadata import annotate_df as _annotate_df
        annotated = _annotate_df(
            candidate_pool_df,
            config.optimization.prefix_to_region,
            config.optimization.region_to_macro,
        )
        pre_count = len(annotated)
        mask = _pd.Series([True] * len(annotated), index=annotated.index)

        # 1. Whitelist by canonical_macro_region
        if interpretation.allowed_macro_regions:
            allowed_set = set(interpretation.allowed_macro_regions)
            mask &= annotated["canonical_macro_region"].isin(allowed_set)

        # 2. Blacklist by broad_super_region (defense-in-depth)
        if interpretation.excluded_super_regions:
            excl_super = set(interpretation.excluded_super_regions)
            mask &= ~annotated["broad_super_region"].isin(excl_super)

        # 3. Blacklist by canonical_region (fine-grained exclusions)
        if interpretation.excluded_regions:
            excl_regions = set(interpretation.excluded_regions)
            mask &= ~annotated["canonical_region"].isin(excl_regions)

        candidate_pool_df = annotated[mask].copy()
        post_count = len(candidate_pool_df)
        excluded_macros = sorted(
            m for m in annotated["canonical_macro_region"].unique()
            if not mask[annotated["canonical_macro_region"] == m].any()
        )
        print(
            f"[profile] candidate_filter: {pre_count} -> {post_count} rows"
        )
        if interpretation.allowed_macro_regions:
            print(f"[profile]   allowed_macro_regions: {sorted(interpretation.allowed_macro_regions)}")
        if interpretation.excluded_super_regions:
            print(f"[profile]   excluded_super_regions: {sorted(interpretation.excluded_super_regions)}")
        if interpretation.excluded_regions:
            print(f"[profile]   excluded_regions: {sorted(interpretation.excluded_regions)}")
        print(f"[profile]   macro_regions excluded: {excluded_macros}")
        _profile_filter_summary = {
            "candidate_count_before": pre_count,
            "candidate_count_after":  post_count,
            "allowed_macro_regions":  sorted(interpretation.allowed_macro_regions),
            "excluded_super_regions": sorted(interpretation.excluded_super_regions),
            "excluded_regions":       sorted(interpretation.excluded_regions),
            "macro_regions_excluded": excluded_macros,
        }
        if post_count == 0:
            raise ValueError(
                f"Profile candidate_filter excluded ALL candidates. "
                f"Allowed macro_regions: {sorted(interpretation.allowed_macro_regions)}"
            )

    if artifact_dir is not None:
        run_id = artifact_dir.name
        run_dir = artifact_dir
    else:
        run_id = _make_run_id()
        run_dir = config.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    bridge = VahaduoBridge()

    with LocalVahaduoServer(config.engine_path, port=config.port) as url:
        print(f"[pipeline] Iterative run {run_id} — server at {url}")

        def engine_runner(panel_text: str, target_text_: str) -> str:
            return run_vahaduo(url, panel_text, target_text_, bridge)

        summary = run_iterations(
            target_text=target_text,
            candidate_pool_df=candidate_pool_df,
            config=config.optimization,
            engine_runner=engine_runner,
            artifact_dir=run_dir,
        )

    _write_iterative_meta(
        run_dir=run_dir,
        run_id=run_id,
        config=config,
        target_file=target_file,
        candidate_pool_file=candidate_pool_file,
        summary=summary,
        interpretation=interpretation,
        profile_name=profile_name,
        profile_filter_summary=_profile_filter_summary,
    )
    return summary


# ---------------------------------------------------------------------------
# Dual-mode output types
# ---------------------------------------------------------------------------

@dataclass
class PeriodRunResult:
    """Outcome of one period sub-run (or a skip record)."""
    period: str
    pool_file: Path
    pool_size: int             # 0 when skipped
    skipped: bool
    skip_reason: str           # empty string when not skipped
    best_distance: float | None
    best_iteration: int | None
    total_iterations: int | None
    stop_reason: str | None
    summary: IterationSummary | None   # None when skipped


@dataclass
class DualModeResult:
    """Complete output of run_dual_mode()."""
    master_run_id: str
    master_dir: Path
    overall_summary: IterationSummary
    period_results: list[PeriodRunResult]


# ---------------------------------------------------------------------------
# Dual-mode entry point
# ---------------------------------------------------------------------------

def run_dual_mode(
    target_file: Path,
    overall_pool_file: Path,
    period_pool_files: dict[str, Path],
    config: Config,
    interpretation: InterpretationConfig | None = None,
    profile_name: str | None = None,
) -> DualModeResult:
    """
    Run the overall optimization followed by one diagnostic run per period.

    Directory layout written under ``config.runs_dir / <master_run_id>/``:

        overall/               full artifact bundle for the primary result
        by_period/
            <period_name>/     full artifact bundle per period
        period_comparison.json

    Parameters
    ----------
    target_file:
        Path to a G25 CSV/TSV target file (one population row).
    overall_pool_file:
        Candidate pool for the primary (overall) run.
    period_pool_files:
        Mapping of period name -> pool CSV path.  Missing or empty files are
        skipped and recorded in period_comparison.json.
    config:
        Pipeline configuration.
    interpretation:
        Optional profile applied to all sub-runs.
    profile_name:
        Display name for the profile.

    Returns
    -------
    DualModeResult
    """
    _ensure_engine(config)

    master_run_id = _make_run_id()
    master_dir = config.runs_dir / master_run_id
    master_dir.mkdir(parents=True, exist_ok=True)
    print(f"[pipeline] Dual-mode run {master_run_id} — master dir: {master_dir}")

    # ── Overall run ────────────────────────────────────────────────────────
    print("[pipeline] Running overall ...")
    overall_dir = master_dir / "overall"
    overall_summary = run_iterative(
        target_file=target_file,
        candidate_pool_file=overall_pool_file,
        config=config,
        interpretation=interpretation,
        profile_name=profile_name,
        artifact_dir=overall_dir,
    )

    # ── Per-period runs ────────────────────────────────────────────────────
    period_results: list[PeriodRunResult] = []
    by_period_dir = master_dir / "by_period"

    for period_name, pool_path in period_pool_files.items():
        print(f"[pipeline] Running period: {period_name} ...")

        # Skip missing files
        if not pool_path.exists():
            print(f"[pipeline]   Skipping {period_name}: pool file not found ({pool_path})")
            period_results.append(PeriodRunResult(
                period=period_name, pool_file=pool_path, pool_size=0,
                skipped=True, skip_reason="pool file not found",
                best_distance=None, best_iteration=None,
                total_iterations=None, stop_reason=None, summary=None,
            ))
            continue

        pool_df = load_g25_file(pool_path)

        # Skip empty pools
        if len(pool_df) == 0:
            print(f"[pipeline]   Skipping {period_name}: pool is empty")
            period_results.append(PeriodRunResult(
                period=period_name, pool_file=pool_path, pool_size=0,
                skipped=True, skip_reason="empty pool",
                best_distance=None, best_iteration=None,
                total_iterations=None, stop_reason=None, summary=None,
            ))
            continue

        period_dir = by_period_dir / period_name
        try:
            period_summary = run_iterative(
                target_file=target_file,
                candidate_pool_file=pool_path,
                config=config,
                interpretation=interpretation,
                profile_name=profile_name,
                artifact_dir=period_dir,
            )
            period_results.append(PeriodRunResult(
                period=period_name, pool_file=pool_path, pool_size=len(pool_df),
                skipped=False, skip_reason="",
                best_distance=period_summary.best_record.result.distance,
                best_iteration=period_summary.best_record.iteration,
                total_iterations=period_summary.total_iterations,
                stop_reason=period_summary.stop_reason,
                summary=period_summary,
            ))
        except Exception as exc:
            print(f"[pipeline]   Period {period_name} failed: {exc}")
            period_results.append(PeriodRunResult(
                period=period_name, pool_file=pool_path, pool_size=len(pool_df),
                skipped=True, skip_reason=f"run error: {exc}",
                best_distance=None, best_iteration=None,
                total_iterations=None, stop_reason=None, summary=None,
            ))

    # ── period_comparison.json ─────────────────────────────────────────────
    _write_period_comparison(master_dir, overall_summary, period_results)

    print(f"[pipeline] Dual-mode complete. Artifacts: {master_dir}")
    return DualModeResult(
        master_run_id=master_run_id,
        master_dir=master_dir,
        overall_summary=overall_summary,
        period_results=period_results,
    )


def _write_period_comparison(
    master_dir: Path,
    overall_summary: IterationSummary,
    period_results: list[PeriodRunResult],
) -> None:
    """Write period_comparison.json to master_dir."""
    completed = [r for r in period_results if not r.skipped]
    ranked = sorted(completed, key=lambda r: r.best_distance)  # type: ignore[arg-type]

    period_entries = []
    for r in period_results:
        entry: dict = {
            "period": r.period,
            "pool_file": str(r.pool_file),
            "pool_size": r.pool_size,
            "skipped": r.skipped,
        }
        if r.skipped:
            entry["skip_reason"] = r.skip_reason
        else:
            entry["best_distance"] = r.best_distance
            entry["best_iteration"] = r.best_iteration
            entry["total_iterations"] = r.total_iterations
            entry["stop_reason"] = r.stop_reason
        period_entries.append(entry)

    doc = {
        "overall_best_distance": overall_summary.best_record.result.distance,
        "overall_best_iteration": overall_summary.best_record.iteration,
        "overall_stop_reason": overall_summary.stop_reason,
        "period_results": period_entries,
        "ranked_by_distance": [
            {"period": r.period, "best_distance": r.best_distance}
            for r in ranked
        ],
    }
    (master_dir / "period_comparison.json").write_text(
        json.dumps(doc, indent=2), encoding="utf-8"
    )


def run_period_diagnostics(
    target_file: Path,
    period_pool_files: dict[str, Path],
    config: Config,
    output_dir: Path,
    overall_distance: float | None = None,
) -> list[PeriodRunResult]:
    """
    Run per-period diagnostic iterations and write period_comparison.json.

    Diagnostics-only — does NOT re-run the overall optimization, so the
    primary best-fit result is never altered.

    Artifacts per period are written to:
        output_dir / by_period / <period_name> /

    period_comparison.json is written to output_dir.
    """
    _ensure_engine(config)

    period_results: list[PeriodRunResult] = []
    by_period_dir = output_dir / "by_period"

    for period_name, pool_path in period_pool_files.items():
        print(f"[pipeline] Period diagnostic: {period_name} ...")

        if not pool_path.exists():
            print(f"[pipeline]   Skipping {period_name}: pool file not found ({pool_path})")
            period_results.append(PeriodRunResult(
                period=period_name, pool_file=pool_path, pool_size=0,
                skipped=True, skip_reason="pool file not found",
                best_distance=None, best_iteration=None,
                total_iterations=None, stop_reason=None, summary=None,
            ))
            continue

        pool_df = load_g25_file(pool_path)

        if len(pool_df) == 0:
            print(f"[pipeline]   Skipping {period_name}: pool is empty")
            period_results.append(PeriodRunResult(
                period=period_name, pool_file=pool_path, pool_size=0,
                skipped=True, skip_reason="empty pool",
                best_distance=None, best_iteration=None,
                total_iterations=None, stop_reason=None, summary=None,
            ))
            continue

        period_artifact_dir = by_period_dir / period_name
        try:
            period_summary = run_iterative(
                target_file=target_file,
                candidate_pool_file=pool_path,
                config=config,
                artifact_dir=period_artifact_dir,
            )
            period_results.append(PeriodRunResult(
                period=period_name, pool_file=pool_path, pool_size=len(pool_df),
                skipped=False, skip_reason="",
                best_distance=period_summary.best_record.result.distance,
                best_iteration=period_summary.best_record.iteration,
                total_iterations=period_summary.total_iterations,
                stop_reason=period_summary.stop_reason,
                summary=period_summary,
            ))
        except Exception as exc:
            print(f"[pipeline]   Period {period_name} failed: {exc}")
            period_results.append(PeriodRunResult(
                period=period_name, pool_file=pool_path, pool_size=len(pool_df),
                skipped=True, skip_reason=f"run error: {exc}",
                best_distance=None, best_iteration=None,
                total_iterations=None, stop_reason=None, summary=None,
            ))

    completed = [r for r in period_results if not r.skipped]
    ranked = sorted(completed, key=lambda r: r.best_distance)  # type: ignore[arg-type]

    period_entries = []
    for r in period_results:
        entry: dict = {
            "period": r.period,
            "pool_file": str(r.pool_file),
            "pool_size": r.pool_size,
            "skipped": r.skipped,
        }
        if r.skipped:
            entry["skip_reason"] = r.skip_reason
        else:
            entry["best_distance"] = r.best_distance
            entry["best_iteration"] = r.best_iteration
            entry["total_iterations"] = r.total_iterations
            entry["stop_reason"] = r.stop_reason
        period_entries.append(entry)

    doc: dict = {
        "period_results": period_entries,
        "ranked_by_distance": [
            {"period": r.period, "best_distance": r.best_distance}
            for r in ranked
        ],
    }
    if overall_distance is not None:
        doc["overall_best_distance"] = overall_distance

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "period_comparison.json").write_text(
        json.dumps(doc, indent=2), encoding="utf-8"
    )
    print(f"[pipeline] Period diagnostics complete -> {output_dir / 'period_comparison.json'}")
    return period_results
