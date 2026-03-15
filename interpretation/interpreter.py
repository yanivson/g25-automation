"""
interpretation/interpreter.py — Deterministic evidence-pack interpretation stage.

Produces three artifacts unconditionally after every pipeline run:
  evidence_pack.json          — full structured evidence (flat schema)
  final_report.json           — merged summary for downstream interpretation
  interpretation_status.json  — machine-readable status marker

No external API calls. No randomness. Always safe to call.
"""

from __future__ import annotations

import json
from pathlib import Path

from interpretation.evidence_pack import EvidencePack, write_evidence_pack


# ---------------------------------------------------------------------------
# Final report builder — pure function, testable without file I/O
# ---------------------------------------------------------------------------

def build_final_report(evidence: EvidencePack) -> dict:
    """
    Build the final_report.json payload from an EvidencePack.

    Pure function — no file I/O. Returns a dict ready for json.dumps().

    Schema
    ------
    {
      "user":         {user_id, display_name, identity_context, ydna_haplogroup},
      "run":          {run_id, profile, best_distance, distance_quality,
                       best_iteration, stop_reason},
      "by_country":   [...],
      "by_macro_region": [...],
      "top_samples":  [...],
      "periods":      {best_period, comparison: [...]},
      "artifacts":    {best_result_json, aggregated_result_json,
                       evidence_pack_json, generic_summary_json,
                       period_comparison_json}
    }
    """
    return {
        "user": {
            "user_id":          evidence.user_id,
            "display_name":     evidence.display_name,
            "identity_context": evidence.identity_context,
            "ydna_haplogroup":  evidence.ydna_haplogroup,
        },
        "run": {
            "run_id":           evidence.run_id,
            "profile":          evidence.profile,
            "best_distance":    evidence.best_distance,
            "distance_quality": evidence.distance_quality,
            "best_iteration":   evidence.best_iteration,
            "stop_reason":      evidence.stop_reason,
        },
        "by_country":      evidence.by_country,
        "by_macro_region": evidence.by_macro_region,
        "top_samples":     evidence.top_samples,
        "periods": {
            "best_period": evidence.period_best,
            "comparison":  evidence.period_comparison,
        },
        "artifacts": {
            "best_result_json":       evidence.artifact_refs.get("best_result_json"),
            "aggregated_result_json": evidence.artifact_refs.get("aggregated_result_json"),
            "evidence_pack_json":     "evidence_pack.json",
            "generic_summary_json":   evidence.artifact_refs.get("generic_summary_json"),
            "period_comparison_json": evidence.artifact_refs.get("period_comparison_json"),
        },
    }


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------

def write_final_report(evidence: EvidencePack, run_dir: Path) -> Path:
    """Write final_report.json into run_dir. Returns the written path."""
    report = build_final_report(evidence)
    out = run_dir / "final_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Main entry point — never raises
# ---------------------------------------------------------------------------

def run_interpretation(run_dir: Path, evidence: EvidencePack) -> None:
    """
    Write all deterministic interpretation artifacts to run_dir.

    Always writes:
      - ``evidence_pack.json``         — full structured evidence (flat)
      - ``final_report.json``          — merged summary for interpretation
      - ``interpretation_status.json`` — status marker for downstream tooling

    Never raises. Safe to call unconditionally after every pipeline run.

    Parameters
    ----------
    run_dir:
        Run artifact directory. All three files are written here.
    evidence:
        Fully built EvidencePack from ``build_evidence_pack()`` or
        ``build_evidence_from_run_dir()``.
    """
    write_evidence_pack(evidence, run_dir)
    write_final_report(evidence, run_dir)
    (run_dir / "interpretation_status.json").write_text(
        json.dumps({"status": "ready_for_interpretation"}, indent=2),
        encoding="utf-8",
    )
    print("[interpretation] evidence_pack.json written.")
    print("[interpretation] final_report.json written.")
    print("[interpretation] Status: ready_for_interpretation")
