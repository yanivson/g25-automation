"""
interpretation/evidence_pack.py — deterministic evidence pack construction.

Builds a structured JSON evidence pack from pipeline run artifacts and
optional user profile metadata. No external calls. Fully deterministic.

The evidence pack is consumed by interpreter.py and by final_report.json
generation, keeping evidence construction testable in isolation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Distance quality classification
# ---------------------------------------------------------------------------

# Ordered list of (upper_bound_exclusive, label). Last entry is the fallback.
_QUALITY_BANDS: list[tuple[float, str]] = [
    (0.020, "excellent fit"),
    (0.035, "close fit"),
    (0.050, "moderate fit"),
]


def classify_distance(distance: float) -> str:
    """Return a human-readable quality label for a best-fit distance value."""
    for threshold, label in _QUALITY_BANDS:
        if distance < threshold:
            return label
    return "poor fit"


# ---------------------------------------------------------------------------
# Evidence pack dataclass
# ---------------------------------------------------------------------------

@dataclass
class EvidencePack:
    """
    Fully deterministic evidence pack built from pipeline outputs.

    All fields are set at construction time. No file I/O happens inside
    this class — the builder function handles data assembly.
    """

    # User metadata — null when no UserProfile is available
    user_id: str | None
    display_name: str | None
    identity_context: str | None
    ydna_haplogroup: str | None

    # Run identity
    run_id: str
    profile: str | None          # interpretation profile name, or null

    # Distance quality
    best_distance: float
    distance_quality: str        # derived via classify_distance()

    # Optimizer outcome — from meta.json
    best_iteration: int | None   # iteration number that produced best_distance
    stop_reason: str | None      # why the optimizer halted

    # Country-level aggregation — from aggregated_result.json
    by_country: list[dict]       # [{"region": str, "percent": float}]

    # Macro-region rollup — from generic_summary.json (empty list if no profile)
    by_macro_region: list[dict]  # [{"macro_region": str, "percent": float, "label": str}]

    # Sample-level populations — from aggregated_result.json
    top_samples: list[dict]      # [{"name": str, "percent": float}]

    # Period diagnostics — empty when no dual run was performed
    period_best: str | None      # period name with lowest non-skipped distance
    period_comparison: list[dict]  # [{"period": str, "best_distance": float, "skipped": bool}]

    # Relative artifact paths within the run directory (for human reference)
    artifact_refs: dict[str, str | None]

    def to_dict(self) -> dict:
        return {
            "user_id":           self.user_id,
            "display_name":      self.display_name,
            "identity_context":  self.identity_context,
            "ydna_haplogroup":   self.ydna_haplogroup,
            "run_id":            self.run_id,
            "profile":           self.profile,
            "best_distance":     self.best_distance,
            "distance_quality":  self.distance_quality,
            "best_iteration":    self.best_iteration,
            "stop_reason":       self.stop_reason,
            "by_country":        self.by_country,
            "by_macro_region":   self.by_macro_region,
            "top_samples":       self.top_samples,
            "period_best":       self.period_best,
            "period_comparison": self.period_comparison,
            "artifact_refs":     self.artifact_refs,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Builder — pure function, no file I/O
# ---------------------------------------------------------------------------

def build_evidence_pack(
    *,
    run_id: str,
    best_distance: float,
    by_country: list[dict],
    top_samples: list[dict],
    by_macro_region: list[dict] | None = None,
    period_comparison: list[dict] | None = None,
    profile_name: str | None = None,
    best_iteration: int | None = None,
    stop_reason: str | None = None,
    user_id: str | None = None,
    display_name: str | None = None,
    identity_context: str | None = None,
    ydna_haplogroup: str | None = None,
    artifact_refs: dict[str, str | None] | None = None,
) -> EvidencePack:
    """
    Build an EvidencePack from pipeline data already in memory.

    All parameters are explicit and deterministic — no file I/O occurs here.
    The caller provides data from either in-memory pipeline results or
    from reading run-directory artifact files.

    Parameters
    ----------
    run_id:
        Identifier of the pipeline run.
    best_distance:
        Best optimized distance value.
    by_country:
        Country-level aggregation list ({"region", "percent"} dicts).
    top_samples:
        Sample-level populations list ({"name", "percent"} dicts).
    by_macro_region:
        Macro-region rollup list. Empty list when no interpretation profile.
    period_comparison:
        Period diagnostic results. Empty list when run was not dual-mode.
        Each entry: {"period": str, "best_distance": float, "skipped": bool}.
    profile_name:
        Interpretation profile name, or None.
    best_iteration:
        The optimizer iteration that produced the best distance.
    stop_reason:
        Why the optimizer halted (e.g. "panel_repeat_streak=2 >= ...").
    user_id, display_name, identity_context, ydna_haplogroup:
        User metadata from UserProfile. All None when unavailable.
    artifact_refs:
        Relative paths within the run directory for key output files.

    Returns
    -------
    EvidencePack
    """
    period_comparison = list(period_comparison or [])
    by_macro_region = list(by_macro_region or [])

    if artifact_refs is None:
        artifact_refs = {
            "aggregated_result_json": "aggregated_result.json",
            "best_result_json":       "best_result.json",
            "generic_summary_json":   None,
            "period_comparison_json": None,
        }

    # Derive period_best: lowest best_distance among non-skipped entries
    non_skipped = [p for p in period_comparison if not p.get("skipped", False)]
    period_best: str | None = None
    if non_skipped:
        period_best = min(non_skipped, key=lambda p: p["best_distance"])["period"]

    return EvidencePack(
        user_id=user_id,
        display_name=display_name,
        identity_context=identity_context,
        ydna_haplogroup=ydna_haplogroup,
        run_id=run_id,
        profile=profile_name,
        best_distance=best_distance,
        distance_quality=classify_distance(best_distance),
        best_iteration=best_iteration,
        stop_reason=stop_reason,
        by_country=by_country,
        by_macro_region=by_macro_region,
        top_samples=top_samples,
        period_best=period_best,
        period_comparison=period_comparison,
        artifact_refs=artifact_refs,
    )


# ---------------------------------------------------------------------------
# Run-directory reader — assembles evidence from on-disk artifacts
# ---------------------------------------------------------------------------

def build_evidence_from_run_dir(
    run_dir: Path,
    *,
    user_id: str | None = None,
    display_name: str | None = None,
    identity_context: str | None = None,
    ydna_haplogroup: str | None = None,
) -> EvidencePack:
    """
    Build an EvidencePack by reading run-directory artifact files.

    Reads: meta.json, aggregated_result.json, and optionally
    generic_summary.json and period_comparison.json.

    Parameters
    ----------
    run_dir:
        Path to the run artifact directory.
    user_id, display_name, identity_context, ydna_haplogroup:
        Optional user metadata to overlay on the artifact-derived evidence.

    Returns
    -------
    EvidencePack
    """
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    agg = json.loads((run_dir / "aggregated_result.json").read_text(encoding="utf-8"))

    by_macro_region: list[dict] = []
    generic_path = run_dir / "generic_summary.json"
    if generic_path.exists():
        generic = json.loads(generic_path.read_text(encoding="utf-8"))
        by_macro_region = generic.get("by_macro_region", [])

    period_comparison: list[dict] = []
    has_period = False
    period_path = run_dir / "period_comparison.json"
    if period_path.exists():
        has_period = True
        pc = json.loads(period_path.read_text(encoding="utf-8"))
        for entry in pc.get("period_results", []):
            period_comparison.append({
                "period":        entry["period"],
                "best_distance": entry.get("best_distance"),
                "skipped":       entry.get("skipped", False),
            })

    artifact_refs: dict[str, str | None] = {
        "aggregated_result_json": "aggregated_result.json",
        "best_result_json":       "best_result.json",
        "generic_summary_json":   "generic_summary.json" if generic_path.exists() else None,
        "period_comparison_json": "period_comparison.json" if has_period else None,
    }

    return build_evidence_pack(
        run_id=meta["run_id"],
        best_distance=meta["best_distance"],
        best_iteration=meta.get("best_iteration"),
        stop_reason=meta.get("stop_reason"),
        by_country=agg.get("by_country", []),
        top_samples=agg.get("top_samples", []),
        by_macro_region=by_macro_region,
        period_comparison=period_comparison,
        profile_name=meta.get("profile"),
        user_id=user_id,
        display_name=display_name,
        identity_context=identity_context,
        ydna_haplogroup=ydna_haplogroup,
        artifact_refs=artifact_refs,
    )


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def write_evidence_pack(evidence: EvidencePack, run_dir: Path) -> Path:
    """Write evidence_pack.json into run_dir. Returns the written path."""
    out = run_dir / "evidence_pack.json"
    out.write_text(evidence.to_json(), encoding="utf-8")
    return out
