"""report/make_report.py — Orchestration and CLI for the HTML report generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .templates import render_report


# ---------------------------------------------------------------------------
# Macro-region rollup
# ---------------------------------------------------------------------------

def _compute_by_macro(
    by_country: list[dict],
    config_path: Path | None = None,
) -> list[dict]:
    """
    Derive by_macro_region from by_country using config.yaml mappings.

    Each country entry's "region" key (population name prefix) is mapped through
    prefix_to_region → region_to_macro → macro_to_label.  Unknown prefixes/regions
    pass through unchanged.

    Returns a list of {"macro_region": str, "percent": float, "label": str}
    sorted by percent descending.  Returns [] if by_country is empty or config
    cannot be loaded.
    """
    if not by_country:
        return []

    # Locate config.yaml — walk up from this file's directory
    if config_path is None:
        candidate = Path(__file__).parent.parent / "config.yaml"
        config_path = candidate if candidate.exists() else None
    if config_path is None or not config_path.exists():
        return []

    try:
        import yaml  # type: ignore
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    interp = raw.get("interpretation") or {}
    prefix_to_region: dict[str, str] = interp.get("prefix_to_region") or {}
    region_to_macro: dict[str, str]  = interp.get("region_to_macro") or {}
    macro_to_label: dict[str, str]   = interp.get("macro_to_label") or {}

    totals: dict[str, float] = {}
    for entry in by_country:
        prefix = str(entry.get("region", ""))
        region = prefix_to_region.get(prefix, prefix)
        macro  = region_to_macro.get(region, region)
        totals[macro] = totals.get(macro, 0.0) + float(entry.get("percent", 0))

    return sorted(
        [
            {
                "macro_region": macro,
                "percent": round(pct, 2),
                "label": macro_to_label.get(macro, ""),
            }
            for macro, pct in totals.items()
        ],
        key=lambda d: d["percent"],
        reverse=True,
    )


# ---------------------------------------------------------------------------
# Analysis freshness + archiving
# ---------------------------------------------------------------------------

def _check_analysis_freshness(user_dir: Path, final_report_path: Path) -> None:
    """
    Warn to stderr if final_report.json is older than key input / config files.

    Checks:
      - <project_root>/config.yaml
      - <user_dir>/input/target.csv

    Prints a single warning if any watched file is newer than the analysis.
    Does not raise — callers should still proceed to generate the report.
    """
    if not final_report_path.exists():
        return

    analysis_mtime = final_report_path.stat().st_mtime

    watch: list[Path] = [
        Path(__file__).parent.parent / "config.yaml",
        user_dir / "input" / "target.csv",
    ]

    import datetime

    for p in watch:
        if p.exists() and p.stat().st_mtime > analysis_mtime:
            delta = datetime.timedelta(seconds=int(p.stat().st_mtime - analysis_mtime))
            print(
                f"[make-report] WARNING: Analysis may be outdated — "
                f"{p.name} is {delta} newer than final_report.json. "
                "Run g25-full-run-user first.",
                file=sys.stderr,
            )
            return  # one warning is enough


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_opt(path: Path) -> dict | list | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _load_text_opt(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


def _normalize_period_doc(raw: dict) -> dict | None:
    """
    Normalise any known period-comparison shape into:
      {"periods": [{"period": ..., "distance": ...}, ...], "best_period": str | None}

    Handles:
      - Real pipeline output (g25-dual-run): period_results[] + best_distance key
      - Legacy / simple format: periods[] or comparison[] + distance key
      - evidence_pack inline format: period_comparison[] + period_best
    """
    # ── Real pipeline format: {"period_results": [...], "ranked_by_distance": [...]} ──
    if "period_results" in raw:
        entries = [
            {"period": r["period"], "distance": r["best_distance"]}
            for r in raw["period_results"]
            if not r.get("skipped") and r.get("best_distance") is not None
        ]
        if not entries:
            return None
        ranked = raw.get("ranked_by_distance") or []
        best = ranked[0]["period"] if ranked else entries[0]["period"]
        return {"periods": entries, "best_period": best}

    # ── Simple / legacy formats ───────────────────────────────────────────────
    periods = raw.get("periods") or raw.get("comparison") or []
    if periods:
        best = raw.get("best_period")
        return {"periods": periods, "best_period": best}

    return None


def _extract_period_data(
    latest: Path,
    final_report: dict,
    evidence_pack: dict | None,
) -> dict | None:
    """
    Resolve and normalise period data from the best available source.

    Priority:
    1. analysis/latest/period_comparison.json  (g25-dual-run output)
    2. evidence_pack.json → period_comparison / period_best
    3. final_report.json → periods.comparison
    """
    raw = _load_json_opt(latest / "period_comparison.json")
    if raw:
        result = _normalize_period_doc(raw)
        if result:
            return result

    ep = evidence_pack or {}
    if ep.get("period_comparison"):
        return {
            "periods": ep["period_comparison"],
            "best_period": ep.get("period_best"),
        }

    fp_periods = final_report.get("periods") or {}
    if fp_periods.get("comparison"):
        return {
            "periods": fp_periods["comparison"],
            "best_period": fp_periods.get("best_period"),
        }

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_report(user_dir: Path | str, theme: str = "dark") -> Path:
    """
    Generate report/index.html for the given user directory.

    Parameters
    ----------
    user_dir:
        Path to ``data/users/<user_id>/``.
    theme:
        Initial color theme: ``'dark'`` (default), ``'light'``, or ``'auto'``.
        The generated report also contains an in-page toggle button.

    Returns
    -------
    Path
        Absolute path to the generated ``report/index.html``.
    """
    user_dir = Path(user_dir).resolve()
    if not user_dir.is_dir():
        raise FileNotFoundError(f"User directory not found: {user_dir}")

    latest = user_dir / "analysis" / "latest"
    if not latest.is_dir():
        raise FileNotFoundError(
            f"No analysis found at analysis/latest/. "
            "Run g25-full-run-user first."
        )

    # Warn early if the analysis JSON looks older than key input/config files.
    _check_analysis_freshness(user_dir, latest / "final_report.json")

    profile         = _load_json(user_dir / "input" / "profile.json")
    final_report    = _load_json(latest / "final_report.json")
    aggregated      = _load_json(latest / "aggregated_result.json")
    generic_summary = _load_json_opt(latest / "generic_summary.json")
    evidence_pack   = _load_json_opt(latest / "evidence_pack.json")

    period_data = _extract_period_data(latest, final_report, evidence_pack)

    interpretation = _load_text_opt(
        user_dir / "interpretation" / "interpretation.txt"
    )

    # Inject initial_panel_strategy as profile when run has no profile field.
    _run = final_report.get("run", {})
    if not _run.get("profile"):
        try:
            import yaml  # type: ignore
            _cfg_path = Path(__file__).parent.parent / "config.yaml"
            _cfg = yaml.safe_load(_cfg_path.read_text(encoding="utf-8"))
            _strategy = (_cfg.get("optimization") or {}).get("initial_panel_strategy", "")
            if _strategy:
                final_report = {**final_report, "run": {**_run, "profile": _strategy}}
        except Exception:
            pass

    # Warn if run_id is absent — indicates an older pipeline version wrote the JSON.
    _run_id = str(final_report.get("run", {}).get("run_id", ""))
    if not _run_id:
        print(
            "[make-report] WARNING: final_report.json has no run_id — "
            "re-run the pipeline to get a fully-tagged analysis.",
            file=sys.stderr,
        )

    # Discard interpretation if it was generated for a different run.
    # interpretation.txt must contain the current run_id somewhere in its text,
    # otherwise treat it as missing (show placeholder instead of stale content).
    if interpretation and _run_id and _run_id not in interpretation:
        interpretation = None

    # Always recompute by_macro_region from the current by_country data so the
    # macro donut reflects this run, not stale generic_summary values.
    by_country = (
        final_report.get("by_country")
        or aggregated.get("by_country", [])
    )
    computed_macro = _compute_by_macro(by_country)
    if computed_macro:
        final_report = {**final_report, "by_macro_region": computed_macro}

    html = render_report(
        profile=profile,
        final_report=final_report,
        aggregated=aggregated,
        generic_summary=generic_summary,
        period_data=period_data,
        interpretation=interpretation,
        theme=theme,
    )

    report_dir = user_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    output = report_dir / "report.html"
    output.write_text(html, encoding="utf-8")
    return output


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cmd_make_report(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="g25-make-report",
        description="Generate a premium HTML report for a user analysis.",
    )
    parser.add_argument("user_dir", help="Path to data/users/<user_id>/")
    parser.add_argument(
        "--theme",
        choices=["dark", "light", "auto"],
        default="dark",
        help="Color theme (default: dark)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output directory (default: <user_dir>/report/)",
    )
    args = parser.parse_args(argv)

    try:
        output = make_report(args.user_dir, theme=args.theme)
        if args.output_dir:
            import shutil
            dest = Path(args.output_dir) / "report.html"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output, dest)
            output = dest
        print(f"[make-report] Report written: {output}")
        print(f"[make-report] Open in browser: file://{output.as_posix()}")
    except FileNotFoundError as exc:
        print(f"[make-report] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cmd_make_report()
