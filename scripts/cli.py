"""
scripts/cli.py — CLI entry points for the G25 automation pipeline.

Commands
--------
g25-preprocess  : Load raw source file, filter, split into period buckets.
g25-build-pool  : Reduce one period bucket to a candidate pool CSV.
g25-run         : Run iterative optimization from a target + candidate pool.
g25-full-run    : One-shot wrapper: preprocess -> build-pool -> run.
g25-dual-run    : Overall run + per-period diagnostic runs in one command.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Shared config loader
# ---------------------------------------------------------------------------

def _load_raw_config(config_path: Path) -> dict:
    import yaml
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def _resolve_config(args_config: str | None) -> tuple[Path, dict]:
    path = Path(args_config) if args_config else Path("config.yaml")
    if not path.exists():
        print(f"[ERROR] Config file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path, _load_raw_config(path)


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:20]


# ---------------------------------------------------------------------------
# g25-preprocess
# ---------------------------------------------------------------------------

def cmd_preprocess(argv: list[str] | None = None) -> None:
    """
    Preprocess a raw G25 source file into per-period bucket CSVs.

    Steps:
      1. Load raw source file
      2. Normalize names
      3. Region filter (writes audit CSVs)
      4. Extract dates
      5. Split by period
      6. Write period CSVs to output directory
    """
    parser = argparse.ArgumentParser(
        prog="g25-preprocess",
        description="Preprocess a raw G25 source file into period bucket CSVs.",
    )
    parser.add_argument("source", help="Path to raw G25 source CSV or TSV.")
    parser.add_argument(
        "--config", default=None,
        help="Path to config.yaml (default: config.yaml in CWD).",
    )
    parser.add_argument(
        "--audit-dir", default=None,
        help="Directory for region-filter audit CSVs (default: from config).",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory for period bucket CSVs (default: from config).",
    )
    args = parser.parse_args(argv)

    config_path, raw = _resolve_config(args.config)
    source_path = Path(args.source)
    if not source_path.exists():
        print(f"[ERROR] Source file not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    audit_dir = Path(args.audit_dir) if args.audit_dir else Path(
        raw.get("data", {}).get("sources_filtered_audit_dir", "data/sources_filtered_audit")
    )
    output_dir = Path(args.output_dir) if args.output_dir else Path(
        raw.get("data", {}).get("sources_periods_dir", "data/sources_periods")
    )

    from preprocessing.loader import load_g25_file
    from preprocessing.normalize_names import add_normalized_name
    from preprocessing.region_filter import RegionConfig, filter_by_region
    from preprocessing.date_extractor import DateConfig, extract_dates
    from preprocessing.split_by_period import split_by_period

    # 1. Load
    print(f"Loading {source_path} ...")
    df = load_g25_file(source_path)
    print(f"  {len(df)} rows loaded.")

    # 2. Normalize
    df = add_normalized_name(df)

    # 3. Region filter
    rf_cfg = raw.get("preprocessing", {}).get("region_filter", {})
    region_config = RegionConfig(
        allowed_keywords=rf_cfg.get("allowed_keywords", []),
        exclusion_keywords=rf_cfg.get("exclusion_keywords", []),
    )
    run_id = _run_id()
    df_filtered = filter_by_region(df, region_config, audit_dir, run_id)
    print(
        f"  Region filter: {len(df_filtered)} kept, {len(df) - len(df_filtered)} removed."
        f"\n  Audit written to {audit_dir}/"
        f"\n    {run_id}_kept.csv"
        f"\n    {run_id}_removed.csv"
    )

    # Drop filter-only columns so period CSVs are clean 26-column G25 files
    g25_columns = ["name"] + [f"dim_{i}" for i in range(1, 26)]
    df_filtered = df_filtered[[c for c in g25_columns if c in df_filtered.columns]]

    # 4. Extract dates
    de_cfg = raw.get("preprocessing", {}).get("date_extraction", {})
    date_config = DateConfig(
        strategy=de_cfg.get("strategy", "unknown"),
        regex_pattern=de_cfg.get("regex_pattern"),
        column_name=de_cfg.get("column_name"),
        metadata_file=de_cfg.get("metadata_file"),
    )
    dates = extract_dates(df_filtered, date_config)
    known = dates.notna().sum()
    print(f"  Date extraction ({date_config.strategy}): {known}/{len(dates)} dated rows.")

    # 5. Split by period
    periods_cfg = raw.get("preprocessing", {}).get("periods", {})
    periods = {name: tuple(bounds) for name, bounds in periods_cfg.items()}
    buckets = split_by_period(df_filtered, dates, periods, output_dir=output_dir)

    # 6. Summary
    print("\nPeriod buckets written:")
    total_rows = 0
    for bucket_name, bucket_df in buckets.items():
        path = output_dir / f"{bucket_name}.csv"
        count = len(bucket_df)
        total_rows += count
        print(f"  {path}  ({count} rows)")
    print(f"\nDone. {total_rows} rows across {len(buckets)} buckets.")


# ---------------------------------------------------------------------------
# g25-build-pool
# ---------------------------------------------------------------------------

def cmd_build_pool(argv: list[str] | None = None) -> None:
    """
    Reduce one period bucket CSV to a candidate pool CSV.

    The output file is ready to pass directly to g25-run.
    """
    parser = argparse.ArgumentParser(
        prog="g25-build-pool",
        description="Reduce a period bucket CSV to a candidate pool CSV.",
    )
    parser.add_argument("period_file", help="Path to a period bucket CSV (e.g. classical.csv).")
    parser.add_argument(
        "--output", default=None,
        help=(
            "Output path for the candidate pool CSV. "
            "Default: data/candidate_pools/<stem>_pool.csv"
        ),
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to config.yaml (default: config.yaml in CWD).",
    )
    parser.add_argument(
        "--clusters-dir", default=None,
        help="Directory for deduplication cluster artifacts (default: from config).",
    )
    args = parser.parse_args(argv)

    config_path, raw = _resolve_config(args.config)
    period_path = Path(args.period_file)
    if not period_path.exists():
        print(f"[ERROR] Period file not found: {period_path}", file=sys.stderr)
        sys.exit(1)

    pools_dir = Path(raw.get("data", {}).get("candidate_pools_dir", "data/candidate_pools"))
    output_path = (
        Path(args.output) if args.output
        else pools_dir / f"{period_path.stem}_pool.csv"
    )
    clusters_dir = Path(args.clusters_dir) if args.clusters_dir else Path(
        raw.get("data", {}).get("candidate_clusters_dir", "data/candidate_clusters")
    )

    from preprocessing.loader import load_g25_file
    from preprocessing.candidate_reducer import CandidateConfig, build_candidate_pool
    from preprocessing.deduplicate_candidates import DeduplicationConfig, deduplicate_candidates

    cr_cfg = raw.get("preprocessing", {}).get("candidate_reduction", {})
    candidate_config = CandidateConfig(
        strategy=cr_cfg.get("strategy", "all"),
        top_n=cr_cfg.get("top_n"),
        allowlist_file=cr_cfg.get("allowlist_file"),
    )
    dd_cfg = raw.get("preprocessing", {}).get("deduplication", {})
    dedup_config = DeduplicationConfig(
        enabled=dd_cfg.get("enabled", True),
        distance_threshold=dd_cfg.get("distance_threshold", 0.0015),
    )

    print(f"Loading {period_path} ...")
    period_df = load_g25_file(period_path)
    print(f"  {len(period_df)} rows loaded.")

    pool = build_candidate_pool(period_df, candidate_config, output_path=None)

    pool_name = period_path.stem + "_pool"
    pool = deduplicate_candidates(
        pool,
        dedup_config,
        target_coords=None,
        artifact_dir=clusters_dir if dedup_config.enabled else None,
        pool_name=pool_name,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pool.to_csv(output_path, index=False)

    print(f"\nCandidate pool written:")
    print(f"  {output_path}  ({len(pool)} populations)")
    if dedup_config.enabled:
        print(f"  Cluster artifacts: {clusters_dir}/")


# ---------------------------------------------------------------------------
# g25-run
# ---------------------------------------------------------------------------

def cmd_run(argv: list[str] | None = None) -> None:
    """
    Run deterministic iterative optimization from a target and candidate pool.

    Writes full artifact bundle to results/runs/<run_id>/.
    Macro-region interpretation and generic_summary.json are only produced
    when --profile is supplied.
    """
    parser = argparse.ArgumentParser(
        prog="g25-run",
        description="Run iterative G25 optimization from target + candidate pool.",
    )
    parser.add_argument("target", help="Path to target G25 CSV (one population row).")
    parser.add_argument("pool", help="Path to candidate pool CSV.")
    parser.add_argument(
        "--config", default=None,
        help="Path to config.yaml (default: config.yaml in CWD).",
    )
    parser.add_argument(
        "--profile", default=None,
        metavar="PROFILE_NAME",
        help=(
            "Interpretation profile name (e.g. 'eastmed_europe'). "
            "Enables macro-region aggregation and writes generic_summary.json. "
            "Profile files live in interpretation_profiles/<name>.yaml."
        ),
    )
    args = parser.parse_args(argv)

    config_path, _ = _resolve_config(args.config)
    target_path = Path(args.target)
    pool_path = Path(args.pool)

    if not target_path.exists():
        print(f"[ERROR] Target file not found: {target_path}", file=sys.stderr)
        sys.exit(1)
    if not pool_path.exists():
        print(f"[ERROR] Pool file not found: {pool_path}", file=sys.stderr)
        sys.exit(1)

    from orchestration.pipeline import load_config, load_profile, run_iterative

    config = load_config(config_path)

    # Load interpretation profile if requested
    interpretation = None
    if args.profile is not None:
        try:
            interpretation = load_profile(args.profile, config.profiles_dir)
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            sys.exit(1)

    print(f"Target:         {target_path}")
    print(f"Candidate pool: {pool_path}")
    print(f"Config:         {config_path}")
    print(f"Profile:        {args.profile or '(none)'}")
    print(f"Max iterations: {config.optimization.max_iterations}")
    print(f"Stop distance:  {config.optimization.stop_distance}")
    print()

    summary = run_iterative(
        target_file=target_path,
        candidate_pool_file=pool_path,
        config=config,
        interpretation=interpretation,
        profile_name=args.profile,
    )

    from optimizer.aggregation import aggregate_by_prefix
    from optimizer.interpretation import build_generic_summary

    best = summary.best_record
    aggregated = aggregate_by_prefix(best.result)

    print()
    print("=" * 50)
    print("Run complete")
    print(f"  Best distance:  {best.result.distance:.8f}")
    print(f"  Best iteration: {best.iteration} / {summary.total_iterations}")
    print(f"  Stop reason:    {summary.stop_reason}")
    print()
    print("By country (prefix aggregation):")
    for agg in aggregated:
        print(f"  {agg.percent:6.2f}%  {agg.region}")
    print()
    print("Top populations at best iteration:")
    for pop in sorted(best.result.populations, key=lambda p: p.percent, reverse=True)[:10]:
        print(f"  {pop.percent:6.2f}%  {pop.name}")

    if interpretation is not None:
        generic = build_generic_summary(best.result, aggregated, interpretation)
        print()
        print("By macro-region:")
        for grp in generic.by_macro_region:
            label_str = f"  [{grp.label}]" if grp.label else ""
            print(f"  {grp.percent:6.2f}%  {grp.macro_region}{label_str}")
        print()
        print("Summary:")
        for line in generic.summary_lines:
            print(f"  {line}")

    print()
    run_dir = config.runs_dir / _find_latest_run(config.runs_dir)
    print(f"Artifacts: {run_dir}/")


def _find_latest_run(runs_dir: Path) -> str:
    """Return the name of the most recently created run directory."""
    dirs = sorted(
        (d for d in runs_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_ctime,
        reverse=True,
    )
    return dirs[0].name if dirs else ""


def _run_interpretation_from_run_dir(
    run_dir: Path,
    *,
    user_id: str | None = None,
    display_name: str | None = None,
    identity_context: str | None = None,
    ydna_haplogroup: str | None = None,
    config_path: Path | None = None,
) -> None:
    """
    Build evidence pack from run_dir artifacts and write interpretation artifacts.

    Accepts optional user metadata that enriches the evidence pack when
    called from cmd_full_run_user (which has a loaded UserProfile).
    When called from cmd_full_run, all user metadata kwargs are None.

    config_path, when provided, is used to:
    - Populate profile with initial_panel_strategy when meta.json has profile=null
    - Compute by_macro_region from by_country when generic_summary.json is absent
    """
    from interpretation.evidence_pack import build_evidence_from_run_dir
    from interpretation.interpreter import run_interpretation

    # Derive profile fallback from config when the run did not use --profile.
    profile_name_fallback: str | None = None
    if config_path is not None and config_path.exists():
        try:
            import yaml  # type: ignore
            _cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            profile_name_fallback = (_cfg.get("optimization") or {}).get(
                "initial_panel_strategy"
            )
        except Exception:  # noqa: BLE001
            pass

    print()
    evidence = build_evidence_from_run_dir(
        run_dir,
        user_id=user_id,
        display_name=display_name,
        identity_context=identity_context,
        ydna_haplogroup=ydna_haplogroup,
        profile_name_fallback=profile_name_fallback,
        config_path=config_path,
    )
    run_interpretation(run_dir, evidence)


# ---------------------------------------------------------------------------
# g25-full-run  (one-shot pipeline wrapper)
# ---------------------------------------------------------------------------

def cmd_full_run(argv: list[str] | None = None) -> None:
    """
    One-shot wrapper: preprocess -> build-pool -> run.

    Performs the complete pipeline from a raw source file and target in a
    single command, using current config defaults for all intermediate steps.

    Pool source options (--pool-source):
      filtered  Use only populations that pass the region filter (default).
      full      Use all populations from the source file, ignoring region filter.
    """
    parser = argparse.ArgumentParser(
        prog="g25-full-run",
        description=(
            "One-shot G25 pipeline: preprocess -> build-pool -> run. "
            "All intermediate files are written to their configured directories."
        ),
    )
    parser.add_argument("target", help="Path to target G25 CSV (one population row).")
    parser.add_argument("source", help="Path to raw G25 source CSV/TSV.")
    parser.add_argument(
        "--config", default=None,
        help="Path to config.yaml (default: config.yaml in CWD).",
    )
    parser.add_argument(
        "--profile", default=None, metavar="PROFILE_NAME",
        help=(
            "Interpretation profile name (e.g. 'eastmed_europe'). "
            "Enables macro-region aggregation and writes generic_summary.json."
        ),
    )
    parser.add_argument(
        "--no-dedup", action="store_true",
        help="Disable candidate deduplication even if enabled in config.",
    )
    parser.add_argument(
        "--pool-source", default="full",
        choices=["filtered", "full"],
        help=(
            "Which population set to use as the candidate pool. "
            "'full' (default): all populations from the source file. "
            "'filtered': only region-filter-passing populations."
        ),
    )
    parser.add_argument(
        "--output-dir", default=None,
        help=(
            "Base directory for intermediate files. "
            "Overrides sources_periods_dir, candidate_pools_dir, and "
            "candidate_clusters_dir from config. "
            "Run artifacts always go to the configured results/runs_dir."
        ),
    )
    args = parser.parse_args(argv)

    config_path, raw = _resolve_config(args.config)
    target_path = Path(args.target)
    source_path = Path(args.source)

    if not target_path.exists():
        print(f"[ERROR] Target file not found: {target_path}", file=sys.stderr)
        sys.exit(1)
    if not source_path.exists():
        print(f"[ERROR] Source file not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    # Resolve intermediate directories (honour --output-dir override)
    base = Path(args.output_dir) if args.output_dir else None
    data_cfg = raw.get("data", {})

    periods_dir = (base / "sources_periods") if base else Path(
        data_cfg.get("sources_periods_dir", "data/sources_periods")
    )
    pools_dir = (base / "candidate_pools") if base else Path(
        data_cfg.get("candidate_pools_dir", "data/candidate_pools")
    )
    audit_dir = Path(data_cfg.get("sources_filtered_audit_dir", "data/sources_filtered_audit"))
    clusters_dir = (base / "candidate_clusters") if base else Path(
        data_cfg.get("candidate_clusters_dir", "data/candidate_clusters")
    )

    print(f"[full-run] Target:      {target_path}")
    print(f"[full-run] Source:      {source_path}")
    print(f"[full-run] Pool source: {args.pool_source}")
    print(f"[full-run] Profile:     {args.profile or '(none)'}")
    print(f"[full-run] Dedup:       {'disabled (--no-dedup)' if args.no_dedup else 'enabled'}")
    print()

    # ── Step 1: Preprocess ─────────────────────────────────────────────────
    print("[full-run] Step 1/3: preprocessing ...")

    from preprocessing.loader import load_g25_file
    from preprocessing.normalize_names import add_normalized_name
    from preprocessing.region_filter import RegionConfig, filter_by_region
    from preprocessing.date_extractor import DateConfig, extract_dates
    from preprocessing.split_by_period import split_by_period

    df = load_g25_file(source_path)
    df = add_normalized_name(df)

    rf_cfg = raw.get("preprocessing", {}).get("region_filter", {})
    region_config = RegionConfig(
        allowed_keywords=rf_cfg.get("allowed_keywords", []),
        exclusion_keywords=rf_cfg.get("exclusion_keywords", []),
    )
    run_id = _run_id()
    df_filtered = filter_by_region(df, region_config, audit_dir, run_id)
    print(f"  Region filter: {len(df_filtered)} kept, {len(df) - len(df_filtered)} removed.")

    g25_columns = ["name"] + [f"dim_{i}" for i in range(1, 26)]
    df_filtered = df_filtered[[c for c in g25_columns if c in df_filtered.columns]]

    de_cfg = raw.get("preprocessing", {}).get("date_extraction", {})
    date_config = DateConfig(
        strategy=de_cfg.get("strategy", "unknown"),
        regex_pattern=de_cfg.get("regex_pattern"),
        column_name=de_cfg.get("column_name"),
        metadata_file=de_cfg.get("metadata_file"),
    )
    dates = extract_dates(df_filtered, date_config)

    periods_cfg = raw.get("preprocessing", {}).get("periods", {})
    periods = {name: tuple(bounds) for name, bounds in periods_cfg.items()}
    split_by_period(df_filtered, dates, periods, output_dir=periods_dir)

    # ── Step 2: Build candidate pool ───────────────────────────────────────
    print("[full-run] Step 2/3: building candidate pool ...")

    from preprocessing.candidate_reducer import CandidateConfig, build_candidate_pool
    from preprocessing.deduplicate_candidates import DeduplicationConfig, deduplicate_candidates

    if args.pool_source == "full":
        # Use all source populations — skip region filter output, re-load raw
        df_for_pool = load_g25_file(source_path)
        df_for_pool = df_for_pool[[c for c in g25_columns if c in df_for_pool.columns]]
        pool_name_stem = source_path.stem + "_full_pool"
    else:
        # Use region-filtered populations
        df_for_pool = df_filtered
        pool_name_stem = source_path.stem + "_pool"

    cr_cfg = raw.get("preprocessing", {}).get("candidate_reduction", {})
    candidate_config = CandidateConfig(
        strategy=cr_cfg.get("strategy", "all"),
        top_n=cr_cfg.get("top_n"),
        allowlist_file=cr_cfg.get("allowlist_file"),
    )
    pool = build_candidate_pool(df_for_pool, candidate_config, output_path=None)

    dd_raw = raw.get("preprocessing", {}).get("deduplication", {})
    dedup_enabled = dd_raw.get("enabled", True) and not args.no_dedup
    dedup_config = DeduplicationConfig(
        enabled=dedup_enabled,
        distance_threshold=dd_raw.get("distance_threshold", 0.010),
    )
    pool = deduplicate_candidates(
        pool, dedup_config,
        target_coords=None,
        artifact_dir=clusters_dir if dedup_enabled else None,
        pool_name=pool_name_stem,
    )

    pools_dir.mkdir(parents=True, exist_ok=True)
    pool_path = pools_dir / f"{pool_name_stem}.csv"
    pool.to_csv(pool_path, index=False)
    print(f"  Pool written: {pool_path}  ({len(pool)} populations)")

    # ── Step 3: Run optimization ───────────────────────────────────────────
    print("[full-run] Step 3/3: running optimization ...")

    from orchestration.pipeline import load_config, load_profile, run_iterative

    config = load_config(config_path)

    interpretation = None
    if args.profile is not None:
        try:
            interpretation = load_profile(args.profile, config.profiles_dir)
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            sys.exit(1)

    summary = run_iterative(
        target_file=target_path,
        candidate_pool_file=pool_path,
        config=config,
        interpretation=interpretation,
        profile_name=args.profile,
    )

    from optimizer.aggregation import aggregate_by_prefix
    from optimizer.interpretation import build_generic_summary

    best = summary.best_record
    aggregated = aggregate_by_prefix(best.result)

    print()
    print("=" * 50)
    print("Full run complete")
    print(f"  Best distance:  {best.result.distance:.8f}")
    print(f"  Best iteration: {best.iteration} / {summary.total_iterations}")
    print(f"  Stop reason:    {summary.stop_reason}")
    print()
    print("By country (prefix aggregation):")
    for agg in aggregated:
        print(f"  {agg.percent:6.2f}%  {agg.region}")
    print()
    print("Top populations at best iteration:")
    for pop in sorted(best.result.populations, key=lambda p: p.percent, reverse=True)[:10]:
        print(f"  {pop.percent:6.2f}%  {pop.name}")

    if interpretation is not None:
        generic = build_generic_summary(best.result, aggregated, interpretation)
        print()
        print("By macro-region:")
        for grp in generic.by_macro_region:
            label_str = f"  [{grp.label}]" if grp.label else ""
            print(f"  {grp.percent:6.2f}%  {grp.macro_region}{label_str}")
        print()
        print("Summary:")
        for line in generic.summary_lines:
            print(f"  {line}")

    print()
    run_dir = config.runs_dir / _find_latest_run(config.runs_dir)
    print(f"Artifacts: {run_dir}/")

    _run_interpretation_from_run_dir(run_dir)


# ---------------------------------------------------------------------------
# Period diagnostics helper for g25-full-run-user
# ---------------------------------------------------------------------------

def _run_period_diagnostics_user(
    config: "Any",
    config_path: "Path",
    user_folder: "Any",
    dest_run_dir: "Path",
    latest_dir: "Path",
) -> None:
    """
    Discover period pool files from config and run one diagnostic pass per
    period.  Writes period_comparison.json to dest_run_dir and copies it to
    latest_dir.  The overall best-fit result is never touched.
    """
    import yaml as _yaml

    with open(config_path, encoding="utf-8") as _f:
        raw = _yaml.safe_load(_f)

    periods_cfg = raw.get("preprocessing", {}).get("periods", {})
    if not periods_cfg:
        return  # no periods defined in config — skip silently

    data_cfg = raw.get("data", {})
    pools_dir = Path(data_cfg.get("candidate_pools_dir", "data/candidate_pools"))
    period_pool_files = {
        name: pools_dir / f"{name}_pool.csv"
        for name in periods_cfg
    }

    available = {k: v for k, v in period_pool_files.items() if v.exists()}
    if not available:
        print("[user-run] Period diagnostics: no pool files found — skipping.")
        return

    print(f"\n[user-run] Running period diagnostics ({len(available)}/{len(period_pool_files)} pools found)...")

    # Read overall distance from the promoted final_report.json
    overall_distance: float | None = None
    fr_path = latest_dir / "final_report.json"
    if fr_path.exists():
        import json as _json
        fr = _json.loads(fr_path.read_text(encoding="utf-8"))
        overall_distance = fr.get("run", {}).get("best_distance")

    from orchestration.pipeline import run_period_diagnostics
    run_period_diagnostics(
        target_file=user_folder.target_file,
        period_pool_files=period_pool_files,
        config=config,
        output_dir=dest_run_dir,
        overall_distance=overall_distance,
    )

    # Copy period_comparison.json into analysis/latest/
    import shutil as _shutil
    src = dest_run_dir / "period_comparison.json"
    if src.exists():
        _shutil.copy2(src, latest_dir / "period_comparison.json")
        print(f"[user-run] period_comparison.json -> {latest_dir}/")


# ---------------------------------------------------------------------------
# g25-full-run-user  (user-folder wrapper around g25-full-run)
# ---------------------------------------------------------------------------

def cmd_full_run_user(argv: list[str] | None = None) -> None:
    """
    Run the full pipeline for a user folder.

    Loads target.csv and profile.json from data/users/<user_id>/ then
    delegates to the standard g25-full-run pipeline unchanged.
    The source dataset and all flags are identical to g25-full-run.
    """
    parser = argparse.ArgumentParser(
        prog="g25-full-run-user",
        description=(
            "One-shot G25 pipeline launched from a user folder. "
            "Loads target.csv and profile.json from data/users/<user_id>/."
        ),
    )
    parser.add_argument(
        "user_dir",
        help="Path to user folder (data/users/<user_id>/).",
    )
    parser.add_argument(
        "source",
        help="Path to raw G25 source CSV/TSV.",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to config.yaml (default: config.yaml in CWD).",
    )
    parser.add_argument(
        "--profile", default=None, metavar="PROFILE_NAME",
        help=(
            "Interpretation profile name (e.g. 'eastmed_europe'). "
            "Enables macro-region aggregation and writes generic_summary.json."
        ),
    )
    parser.add_argument(
        "--no-dedup", action="store_true",
        help="Disable candidate deduplication even if enabled in config.",
    )
    parser.add_argument(
        "--pool-source", default="full",
        choices=["filtered", "full"],
        help=(
            "Which population set to use as the candidate pool. "
            "'full' (default): all populations from the source file. "
            "'filtered': only region-filter-passing populations."
        ),
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Base directory for intermediate files.",
    )
    args = parser.parse_args(argv)

    from orchestration.user_profile import load_user_folder
    from orchestration.user_layout import (
        UserLayout,
        ensure_user_dirs,
        ensure_interpretation_stub,
        promote_to_latest,
    )

    user_dir = Path(args.user_dir)
    layout = UserLayout(user_dir)

    try:
        user_folder = load_user_folder(user_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"[ERROR] Source file not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    # Ensure user subdirectory tree exists before the run
    ensure_user_dirs(layout)

    # Print user context header
    p = user_folder.profile
    print(f"[user-run] User:    {p.user_id} ({p.display_name})")
    if p.identity_context:
        print(f"[user-run] Context: {p.identity_context}")
    if p.ydna_haplogroup:
        print(f"[user-run] Y-DNA:   {p.ydna_haplogroup}")
    print()

    # Build argv and delegate to cmd_full_run (writes to config.runs_dir)
    full_run_argv: list[str] = [str(user_folder.target_file), args.source]
    if args.profile:
        full_run_argv += ["--profile", args.profile]
    if args.no_dedup:
        full_run_argv.append("--no-dedup")
    full_run_argv += ["--pool-source", args.pool_source]
    if args.output_dir:
        full_run_argv += ["--output-dir", args.output_dir]
    if args.config:
        full_run_argv += ["--config", args.config]

    cmd_full_run(full_run_argv)

    # Move the freshly written run dir into the user-centric tree.
    # cmd_full_run wrote it to config.runs_dir/<run_id>/; we relocate it
    # to analysis/runs/<run_id>/ and re-run interpretation with user metadata.
    import shutil
    from orchestration.pipeline import load_config
    config_path = Path(args.config) if args.config else Path("config.yaml")
    config = load_config(config_path)
    run_id = _find_latest_run(config.runs_dir)
    src_run_dir = config.runs_dir / run_id
    dest_run_dir = layout.runs_dir / run_id
    shutil.move(str(src_run_dir), str(dest_run_dir))
    print(f"\n[user-run] Run dir  -> {dest_run_dir}/")

    # Create interpretation stub if the user has not written one yet
    created = ensure_interpretation_stub(layout)
    if created:
        print(f"[user-run] Created  {layout.interpretation_txt}")

    # ── Period diagnostics first — writes period_comparison.json to dest_run_dir ──
    # Must run before interpretation so evidence_pack / final_report include
    # period fields populated from the freshly written period_comparison.json.
    _run_period_diagnostics_user(
        config=config,
        config_path=config_path,
        user_folder=user_folder,
        dest_run_dir=dest_run_dir,
        latest_dir=layout.latest_dir,
    )

    # ── Write interpretation artifacts after period diagnostics are complete ──
    # period_comparison.json now exists in dest_run_dir, so evidence_pack and
    # final_report will include period_best + period_comparison, profile, and
    # by_macro_region derived from config.yaml mappings.
    _run_interpretation_from_run_dir(
        dest_run_dir,
        user_id=p.user_id,
        display_name=p.display_name,
        identity_context=p.identity_context,
        ydna_haplogroup=p.ydna_haplogroup,
        config_path=config_path,
    )

    # Promote all artifacts (including period_comparison + fresh interpretation)
    copied = promote_to_latest(dest_run_dir, layout)
    print(f"[user-run] latest/  -> {len(copied)} files promoted.")

    # ── Generate HTML report from the freshly-promoted analysis/latest/ ──────
    try:
        from report.make_report import make_report as _make_report
        report_path = _make_report(user_dir)
        print(f"[user-run] Report   -> {report_path}")
        print(f"[user-run] Open in browser: file://{report_path.as_posix()}")
    except Exception as exc:  # noqa: BLE001
        print(f"[user-run] WARNING: Report generation failed: {exc}", file=sys.stderr)

    print(f"[user-run] Done.    {user_dir}/")


# ---------------------------------------------------------------------------
# g25-dual-run
# ---------------------------------------------------------------------------

def cmd_dual_run(argv: list[str] | None = None) -> None:
    """
    Run the overall optimization then one diagnostic run per period bucket.

    Period pool files are auto-discovered from --periods-dir based on period
    names in config.yaml (preprocessing.periods).  For each period name, the
    command looks for <periods_dir>/<period_name>_pool.csv.  Missing or empty
    files are skipped and recorded in period_comparison.json.

    Artifacts are written to:
      results/runs/<master_run_id>/
        overall/              primary result
        by_period/
          <period_name>/      diagnostic result per period
        period_comparison.json
    """
    parser = argparse.ArgumentParser(
        prog="g25-dual-run",
        description=(
            "Run overall optimization + per-period diagnostic runs. "
            "Writes a structured artifact bundle with period_comparison.json."
        ),
    )
    parser.add_argument("target", help="Path to target G25 CSV (one population row).")
    parser.add_argument("overall_pool", help="Path to the overall candidate pool CSV.")
    parser.add_argument(
        "--config", default=None,
        help="Path to config.yaml (default: config.yaml in CWD).",
    )
    parser.add_argument(
        "--profile", default=None, metavar="PROFILE_NAME",
        help="Interpretation profile name applied to all sub-runs.",
    )
    parser.add_argument(
        "--periods-dir", default=None, metavar="DIR",
        help=(
            "Directory containing period pool CSVs. "
            "Default: candidate_pools_dir from config. "
            "Expects files named <period_name>_pool.csv."
        ),
    )
    args = parser.parse_args(argv)

    config_path, raw = _resolve_config(args.config)
    target_path = Path(args.target)
    overall_pool_path = Path(args.overall_pool)

    if not target_path.exists():
        print(f"[ERROR] Target file not found: {target_path}", file=sys.stderr)
        sys.exit(1)
    if not overall_pool_path.exists():
        print(f"[ERROR] Overall pool file not found: {overall_pool_path}", file=sys.stderr)
        sys.exit(1)

    from orchestration.pipeline import load_config, load_profile, run_dual_mode

    config = load_config(config_path)

    # Resolve periods directory
    data_cfg = raw.get("data", {})
    periods_dir = Path(args.periods_dir) if args.periods_dir else Path(
        data_cfg.get("candidate_pools_dir", "data/candidate_pools")
    )

    # Discover period pool files from config period names
    periods_cfg = raw.get("preprocessing", {}).get("periods", {})
    period_pool_files: dict[str, Path] = {
        period_name: periods_dir / f"{period_name}_pool.csv"
        for period_name in periods_cfg
    }

    # Load interpretation profile if requested
    interpretation = None
    if args.profile is not None:
        try:
            interpretation = load_profile(args.profile, config.profiles_dir)
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            sys.exit(1)

    print(f"Target:        {target_path}")
    print(f"Overall pool:  {overall_pool_path}")
    print(f"Profile:       {args.profile or '(none)'}")
    print(f"Periods dir:   {periods_dir}")
    print(f"Period pools:")
    for name, path in period_pool_files.items():
        status = "found" if path.exists() else "not found — will skip"
        print(f"  {name}: {path}  [{status}]")
    print()

    result = run_dual_mode(
        target_file=target_path,
        overall_pool_file=overall_pool_path,
        period_pool_files=period_pool_files,
        config=config,
        interpretation=interpretation,
        profile_name=args.profile,
    )

    # Print comparison summary
    overall = result.overall_summary.best_record

    print()
    print("=" * 60)
    print("Dual run complete")
    print()
    print(f"  Overall best distance:  {overall.result.distance:.8f}")
    print(f"  Overall best iteration: {overall.iteration} / "
          f"{result.overall_summary.total_iterations}")
    print(f"  Overall stop reason:    {result.overall_summary.stop_reason}")
    print()
    completed = [pr for pr in result.period_results if not pr.skipped]
    if not completed:
        print("Per-period runs skipped: no dated period pools were generated for this dataset.")
    else:
        print("Period results:")
        for pr in result.period_results:
            if pr.skipped:
                print(f"  {pr.period:<20}  SKIPPED  ({pr.skip_reason})")
            else:
                print(
                    f"  {pr.period:<20}  dist={pr.best_distance:.8f}"
                    f"  iter={pr.best_iteration}/{pr.total_iterations}"
                )
        print()
        best_period = min(completed, key=lambda pr: pr.best_distance)
        print(f"  Best period: {best_period.period}  ({best_period.best_distance:.8f})")
    print()
    print(f"Artifacts: {result.master_dir}/")
