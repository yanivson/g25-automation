"""report/make_report.py — Orchestration and CLI for the HTML report generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .templates import render_report


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
            f"No analysis/latest/ found under {user_dir}. "
            "Run g25-full-run-user first."
        )

    profile         = _load_json(user_dir / "input" / "profile.json")
    final_report    = _load_json(latest / "final_report.json")
    aggregated      = _load_json(latest / "aggregated_result.json")
    generic_summary = _load_json_opt(latest / "generic_summary.json")
    evidence_pack   = _load_json_opt(latest / "evidence_pack.json")

    period_data = _extract_period_data(latest, final_report, evidence_pack)

    interpretation = _load_text_opt(
        user_dir / "interpretation" / "interpretation.txt"
    )

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
