"""
scripts/pipeline_validation.py — structural pipeline integrity validator.

Validates pipeline runs and the candidate corpus on purely structural criteria:

  A. Artifact presence and consistency
  B. Candidate pool composition by macro-region
  C. Preselection coverage by macro-region
  D. Top-reference quality flags (outlier-suffix samples, unmapped prefixes)
  E. Macro-aggregation sum consistency
  F. Stop-reason classification
  G. Corpus-level reachability

No ancestry expectations, ethnicity labels, or expected outcome comparisons
are included anywhere in this file.  Validation is structural only.

Usage
-----
    python -m scripts.pipeline_validation                        # corpus only
    python -m scripts.pipeline_validation --users Ryan Rivka    # per-user runs
    python -m scripts.pipeline_validation --users Ryan Rivka yaniv --config config.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants — structural thresholds, no ethnicity content
# ---------------------------------------------------------------------------

# Major macro-regions: zero reachable = pipeline error regardless of target
_MAJOR_MACRO_REGIONS: frozenset[str] = frozenset({
    "Northwestern Europe",
    "Western Europe",
    "Central Europe",
    "Southern Europe",
    "Southeastern Europe",
    "Northeastern Europe",
    "Eastern Mediterranean",
    "Middle East",
    "Caucasus",
    "North Africa",
})

# Required artifact files in a complete run directory
_REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "meta.json",
    "best_result.json",
    "aggregated_result.json",
    "preselection.csv",
    "run_summary.json",
)
_OPTIONAL_ARTIFACTS: tuple[str, ...] = (
    "evidence_pack.json",
    "period_comparison.json",
)

# Distance bounds for quality classification
_DISTANCE_GOOD = 0.015
_DISTANCE_ACCEPTABLE = 0.025
_DISTANCE_WARN = 0.035

# Outlier-suffix pattern — mirrors outlier_filter.py exactly.
# Structural flag only; no ethnic inference.
_OUTLIER_SUFFIX = re.compile(r"_o[A-Z]|_o[0-9]|_o$|_o\.")

# Stop reasons that indicate a structural problem
_WARN_STOP_REASONS: frozenset[str] = frozenset({
    "candidate pool exhausted",
    "max_iterations reached",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config(config_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Return (prefix_to_region, region_to_macro) from config.yaml."""
    import yaml
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    interp = raw.get("interpretation", {})
    return (
        interp.get("prefix_to_region", {}),
        interp.get("region_to_macro", {}),
    )


def _annotate_names(
    names: list[str],
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
) -> list[dict[str, str]]:
    """Return per-name annotation dicts with prefix/region/macro/outlier_flag."""
    known_macros = set(region_to_macro.values())
    result = []
    for name in names:
        prefix = name.split("_")[0]
        region = prefix_to_region.get(prefix, prefix)
        macro = region_to_macro.get(region, region)
        is_unmapped = macro not in known_macros
        has_outlier_suffix = bool(_OUTLIER_SUFFIX.search(name))
        result.append({
            "name": name,
            "prefix": prefix,
            "canonical_region": region,
            "canonical_macro_region": macro,
            "unmapped": is_unmapped,
            "outlier_suffix": has_outlier_suffix,
        })
    return result


def _percent_sum(items: list[dict[str, Any]], key: str = "percent") -> float:
    return sum(float(x.get(key, 0)) for x in items)


def _distance_quality(d: float) -> str:
    if d <= _DISTANCE_GOOD:
        return "good"
    if d <= _DISTANCE_ACCEPTABLE:
        return "acceptable"
    if d <= _DISTANCE_WARN:
        return "warn"
    return "poor"


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------

class _Report:
    """Accumulates findings for one validation target."""

    def __init__(self, label: str) -> None:
        self.label = label
        self._errors: list[str] = []
        self._warnings: list[str] = []
        self._info: list[str] = []

    def error(self, msg: str) -> None:
        self._errors.append(msg)

    def warn(self, msg: str) -> None:
        self._warnings.append(msg)

    def info(self, msg: str) -> None:
        self._info.append(msg)

    def print(self) -> None:
        sep = "=" * 64
        print(f"\n{sep}")
        print(f"VALIDATION: {self.label}")
        print(sep)
        for m in self._info:
            print(f"  [INFO]  {m}")
        for m in self._warnings:
            print(f"  [WARN]  {m}")
        for m in self._errors:
            print(f"  [ERROR] {m}")
        if not self._errors and not self._warnings:
            print("  PASS — no structural issues found.")
        elif not self._errors:
            print(f"  PASS with {len(self._warnings)} warning(s).")
        else:
            print(f"  FAIL — {len(self._errors)} error(s), {len(self._warnings)} warning(s).")

    @property
    def error_count(self) -> int:
        return len(self._errors)

    @property
    def warning_count(self) -> int:
        return len(self._warnings)


# ---------------------------------------------------------------------------
# A. Artifact presence and consistency
# ---------------------------------------------------------------------------

def check_artifacts(run_dir: Path, report: _Report) -> dict[str, Any]:
    """Check all expected artifacts are present and internally consistent."""
    present: dict[str, Any] = {}

    for fname in _REQUIRED_ARTIFACTS:
        p = run_dir / fname
        if not p.exists():
            report.error(f"Required artifact missing: {fname}")
        else:
            report.info(f"Artifact present: {fname}")
            if fname.endswith(".json"):
                try:
                    present[fname] = json.loads(p.read_text(encoding="utf-8"))
                except Exception as e:
                    report.error(f"Cannot parse {fname}: {e}")

    for fname in _OPTIONAL_ARTIFACTS:
        p = run_dir / fname
        if p.exists():
            report.info(f"Optional artifact present: {fname}")
            try:
                present[fname] = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                report.warn(f"Cannot parse optional {fname}: {e}")
        else:
            report.info(f"Optional artifact absent: {fname}")

    # Cross-file consistency
    meta = present.get("meta.json", {})
    best = present.get("best_result.json", {})
    if meta and best:
        meta_dist = float(meta.get("best_distance", -1))
        best_dist = float(best.get("distance", -2))
        if abs(meta_dist - best_dist) > 1e-5:
            report.error(
                f"Distance mismatch: meta.best_distance={meta_dist:.7f} "
                f"vs best_result.distance={best_dist:.7f}"
            )

        meta_iter = int(meta.get("total_iterations", 0))
        best_iter = int(best.get("iteration", 0))
        if best_iter > meta_iter:
            report.error(
                f"best_result.iteration={best_iter} > meta.total_iterations={meta_iter}"
            )

        profile = meta.get("profile", "")
        if not profile:
            report.warn("meta.json: profile field is empty")
        else:
            report.info(f"Profile: {profile!r}")

        # Evidence pack profile consistency
        # Only flag a mismatch when both sides have non-empty values that differ.
        ev = present.get("evidence_pack.json", {})
        if ev:
            ev_profile = ev.get("profile", "")
            if profile and ev_profile and ev_profile != profile:
                report.error(
                    f"Profile mismatch: meta.json={profile!r} vs evidence_pack.json={ev_profile!r}"
                )

    return present


# ---------------------------------------------------------------------------
# B. Preselection coverage
# ---------------------------------------------------------------------------

def check_preselection(
    run_dir: Path,
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    report: _Report,
) -> None:
    """Check which macro-regions are represented in the preselection."""
    psel_path = run_dir / "preselection.csv"
    if not psel_path.exists():
        return

    import pandas as pd
    psel = pd.read_csv(psel_path)
    names = psel["name"].tolist()
    annotated = _annotate_names(names, prefix_to_region, region_to_macro)

    total = len(annotated)
    macros_present: dict[str, int] = {}
    outlier_in_psel: list[str] = []
    unmapped_in_psel: list[str] = []

    for ann in annotated:
        m = ann["canonical_macro_region"]
        macros_present[m] = macros_present.get(m, 0) + 1
        if ann["outlier_suffix"]:
            outlier_in_psel.append(ann["name"])
        if ann["unmapped"]:
            unmapped_in_psel.append(ann["name"])

    report.info(f"Preselection: {total} candidates across {len(macros_present)} macro-regions")
    for macro in sorted(macros_present, key=lambda k: -macros_present[k]):
        report.info(f"  preselection [{macro}]: {macros_present[macro]}")

    for major in sorted(_MAJOR_MACRO_REGIONS):
        if major not in macros_present:
            # Only error if pool actually has samples from this region
            # (handled in corpus check; here we just report absence)
            report.warn(f"Preselection: major macro-region absent: {major!r}")

    if outlier_in_psel:
        report.warn(
            f"Preselection: {len(outlier_in_psel)} samples have outlier-style suffix "
            f"(not excluded by current _o[A-Z] filter): "
            + ", ".join(outlier_in_psel[:5])
            + ("..." if len(outlier_in_psel) > 5 else "")
        )

    if unmapped_in_psel:
        report.warn(
            f"Preselection: {len(unmapped_in_psel)} samples with unmapped prefix "
            f"(pass-through macro): "
            + ", ".join(unmapped_in_psel[:3])
            + ("..." if len(unmapped_in_psel) > 3 else "")
        )


# ---------------------------------------------------------------------------
# C. Top-reference quality
# ---------------------------------------------------------------------------

def check_top_references(
    artifacts: dict[str, Any],
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    report: _Report,
) -> None:
    """Structural checks on the best-result populations."""
    best = artifacts.get("best_result.json", {})
    if not best:
        return

    distance = float(best.get("distance", 999))
    dq = _distance_quality(distance)
    report.info(f"Best distance: {distance:.7f} ({dq})")
    if dq == "poor":
        report.error(f"Best distance {distance:.4f} exceeds poor-fit threshold {_DISTANCE_WARN}")
    elif dq == "warn":
        report.warn(f"Best distance {distance:.4f} above acceptable threshold {_DISTANCE_ACCEPTABLE}")

    populations = best.get("populations", [])
    if not populations:
        report.error("best_result.json: no populations found")
        return

    total_pct = _percent_sum(populations)
    if abs(total_pct - 100.0) > 1.5:
        report.warn(f"Population percents sum to {total_pct:.1f}% (expected ~100%)")

    annotated = _annotate_names(
        [p["name"] for p in populations],
        prefix_to_region, region_to_macro
    )

    outlier_top: list[tuple[str, float]] = []
    for pop, ann in zip(populations, annotated):
        if ann["outlier_suffix"]:
            outlier_top.append((pop["name"], float(pop.get("percent", 0))))

    if outlier_top:
        names_pcts = ", ".join(f"{n} ({p:.1f}%)" for n, p in outlier_top)
        report.warn(
            f"Top contributors with outlier-style suffix "
            f"(may have shifted coordinates): {names_pcts}"
        )

    report.info(f"Contributing populations: {len(populations)}")
    for pop, ann in zip(populations, annotated):
        report.info(
            f"  {pop['name']:<50} {pop.get('percent', 0):>6.1f}%  "
            f"[{ann['canonical_macro_region']}]"
            + ("  [outlier-suffix]" if ann["outlier_suffix"] else "")
            + ("  [unmapped]" if ann["unmapped"] else "")
        )


# ---------------------------------------------------------------------------
# D. Macro-aggregation consistency
# ---------------------------------------------------------------------------

def check_macro_aggregation(
    artifacts: dict[str, Any],
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    report: _Report,
) -> None:
    """Verify macro aggregation sums and prefix mappings are consistent."""
    agg = artifacts.get("aggregated_result.json", {})
    if not agg:
        return

    by_country = agg.get("by_country", [])
    if not by_country:
        report.warn("aggregated_result.json: by_country is empty")
        return

    total = _percent_sum(by_country)
    if abs(total - 100.0) > 1.5:
        report.warn(f"by_country percents sum to {total:.1f}% (expected ~100%)")

    unmapped_regions: list[tuple[str, float]] = []
    for entry in by_country:
        region = str(entry.get("region", ""))
        pct = float(entry.get("percent", 0))
        if region not in prefix_to_region and region not in region_to_macro.values():
            # Check if it maps as a prefix
            macro = region_to_macro.get(
                prefix_to_region.get(region, region), region
            )
            if macro == region and region not in region_to_macro:
                unmapped_regions.append((region, pct))

    if unmapped_regions:
        names = ", ".join(f"{r} ({p:.1f}%)" for r, p in unmapped_regions)
        report.warn(f"by_country entries with no config mapping: {names}")

    # Evidence pack macro-region sum
    ev = artifacts.get("evidence_pack.json", {})
    if ev:
        by_macro = ev.get("by_macro_region", [])
        macro_sum = _percent_sum(by_macro)
        if abs(macro_sum - 100.0) > 1.5:
            report.warn(
                f"evidence_pack.by_macro_region sums to {macro_sum:.1f}% (expected ~100%)"
            )
        else:
            report.info(f"evidence_pack.by_macro_region sum: {macro_sum:.1f}%")
            for entry in by_macro:
                report.info(
                    f"  {entry.get('macro_region', '?'):<32} {entry.get('percent', 0):>6.1f}%"
                )

    # Cross-check: sum of by_country should equal sum of by_macro (both ~100%)
    # Already checked both above.


# ---------------------------------------------------------------------------
# E. Stop-reason check
# ---------------------------------------------------------------------------

def check_stop_reason(artifacts: dict[str, Any], report: _Report) -> None:
    meta = artifacts.get("meta.json", {})
    if not meta:
        return
    stop = meta.get("stop_reason", "")
    n_iter = meta.get("total_iterations", "?")
    panel_size = meta.get("final_panel_size", "?")
    exhausted = meta.get("exhausted_count", "?")

    report.info(f"Stop reason: {stop!r}")
    report.info(f"Iterations: {n_iter}  |  Final panel size: {panel_size}  |  Exhausted: {exhausted}")

    for warn_stem in _WARN_STOP_REASONS:
        if warn_stem.lower() in stop.lower():
            report.warn(
                f"Stop reason suggests optimization may not have converged: {stop!r}"
            )
            break


# ---------------------------------------------------------------------------
# F. Corpus reachability check
# ---------------------------------------------------------------------------

def check_corpus(
    pool_path: Path,
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    report: _Report,
) -> None:
    """Structural corpus coverage — no ethnicity content."""
    import pandas as pd
    from preprocessing.sample_metadata import annotate_df

    df = pd.read_csv(pool_path)
    annotated = annotate_df(df, prefix_to_region, region_to_macro)
    total = len(annotated)
    outlier_n = int(annotated["is_outlier_adjusted"].sum())
    std = annotated[annotated["allowed_in_standard_mode"]]
    std_n = len(std)

    report.info(f"Corpus: {total} total, {outlier_n} outlier-adjusted, {std_n} standard-mode")

    known_macros = set(region_to_macro.values())
    macro_counts: dict[str, int] = std["canonical_macro_region"].value_counts().to_dict()

    for macro in sorted(macro_counts, key=lambda k: -macro_counts[k]):
        known_flag = "" if macro in known_macros else "  [unmapped]"
        report.info(f"  corpus [{macro}]: {macro_counts[macro]}{known_flag}")

    errors = 0
    for major in sorted(_MAJOR_MACRO_REGIONS):
        count = macro_counts.get(major, 0)
        if count == 0:
            report.error(f"Corpus: zero standard-mode samples for major macro-region: {major!r}")
            errors += 1
        elif count < 3:
            report.warn(f"Corpus: only {count} standard-mode sample(s) for {major!r}")

    # Verify the filter coverage matches the corpus annotation.
    # After the broadened pattern fix, caught == all outlier variants.
    caught_n = int(annotated["is_outlier_adjusted"].sum())
    report.info(f"Corpus: outlier filter excludes {caught_n} samples total")


# ---------------------------------------------------------------------------
# Full per-run validation
# ---------------------------------------------------------------------------

def validate_run(
    run_dir: Path,
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    label: str | None = None,
) -> _Report:
    report = _Report(label or str(run_dir))

    artifacts = check_artifacts(run_dir, report)
    check_stop_reason(artifacts, report)
    check_preselection(run_dir, prefix_to_region, region_to_macro, report)
    check_top_references(artifacts, prefix_to_region, region_to_macro, report)
    check_macro_aggregation(artifacts, prefix_to_region, region_to_macro, report)

    return report


def validate_user(
    user_id: str,
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    users_base: Path = Path("data/users"),
) -> _Report:
    """Find the latest non-named run for *user_id* and validate it."""
    runs_dir = users_base / user_id / "analysis" / "runs"
    if not runs_dir.exists():
        r = _Report(f"user:{user_id}")
        r.error(f"Runs directory not found: {runs_dir}")
        return r

    # Sort timestamped runs (format YYYYMMDD_HHMMSS_NNNN)
    run_dirs = sorted(
        (d for d in runs_dir.iterdir() if d.is_dir() and re.match(r"\d{8}_", d.name)),
        key=lambda d: d.name,
    )
    if not run_dirs:
        # Fall back to any run dir
        run_dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir())

    if not run_dirs:
        r = _Report(f"user:{user_id}")
        r.error(f"No run directories found in {runs_dir}")
        return r

    latest = run_dirs[-1]
    return validate_run(
        latest,
        prefix_to_region,
        region_to_macro,
        label=f"user:{user_id}  run:{latest.name}",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pipeline-validate",
        description="Structural G25 pipeline integrity validation.",
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--pool",
        default="data/candidate_pools/full_ancient_pool_dedup.csv",
        help="Candidate pool CSV for corpus-level checks",
    )
    parser.add_argument(
        "--users", nargs="*", default=[],
        help="User IDs to validate latest runs for",
    )
    parser.add_argument(
        "--run-dir", default=None,
        help="Validate a specific run directory directly",
    )
    parser.add_argument(
        "--no-corpus", action="store_true",
        help="Skip corpus-level checks",
    )
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    prefix_to_region, region_to_macro = _load_config(config_path)

    total_errors = 0
    total_warnings = 0

    # Corpus check
    if not args.no_corpus:
        pool_path = Path(args.pool)
        if pool_path.exists():
            r = _Report(f"corpus:{pool_path.name}")
            check_corpus(pool_path, prefix_to_region, region_to_macro, r)
            r.print()
            total_errors += r.error_count
            total_warnings += r.warning_count
        else:
            print(f"[WARN] Pool not found: {pool_path}")

    # Per-user run validation
    for user_id in (args.users or []):
        r = validate_user(user_id, prefix_to_region, region_to_macro)
        r.print()
        total_errors += r.error_count
        total_warnings += r.warning_count

    # Direct run-dir validation
    if args.run_dir:
        r = validate_run(
            Path(args.run_dir), prefix_to_region, region_to_macro,
            label=f"run-dir:{args.run_dir}",
        )
        r.print()
        total_errors += r.error_count
        total_warnings += r.warning_count

    # Final summary
    sep = "=" * 64
    print(f"\n{sep}")
    print(f"SUMMARY: {total_errors} error(s), {total_warnings} warning(s)")
    print(sep)

    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
