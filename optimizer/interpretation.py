"""
optimizer/interpretation.py — config-driven generic summary generation.

Three-layer output model:
  Layer 1 (engine output):     RunResult.populations     — individual sample percentages
  Layer 2 (prefix aggregation): list[AggregatedPopulation] — per-country/prefix sums
  Layer 3 (interpretation):    GenericSummary             — macro-region rollup + summary text

All mappings are config-driven. No ethnicity-specific logic or target-specific
branching exists anywhere in this module. The same code serves Ashkenazi,
Scottish, Levantine, North African, or any other target identically.

Fallback rule:
  If a prefix is not found in prefix_to_region, the prefix is used as the region.
  If a region is not found in region_to_macro, the region is used as the macro-region.
  If a macro-region is not found in macro_to_label, label is an empty string.
  This guarantees the function always produces output for any input.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.result_parser import RunResult
from optimizer.aggregation import AggregatedPopulation


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class InterpretationConfig:
    """
    Config-driven mappings for the three-layer interpretation pipeline.

    All mappings default to empty dicts so the module works even when the
    config file has no interpretation section (fallthrough behaviour applies).

    Candidate universe filtering (all metadata-driven, no name substring matching):
        allowed_macro_regions:
            Keep only candidates whose ``canonical_macro_region`` is in this list.
            Empty list = no macro-region restriction (standard behaviour).
        excluded_super_regions:
            Additionally drop candidates whose ``broad_super_region`` is in this set.
            Applied after allowed_macro_regions as defense-in-depth.
        excluded_regions:
            Additionally drop candidates whose ``canonical_region`` is in this set.

    Profile metadata:
        profile_label:  Human-readable one-line description shown in reports.
        use_standard_mode:  Respect allowed_in_standard_mode column (default True).
        apply_plausibility_constraints / apply_remedy_passes: passed through to
            optimizer config (future use; current optimizer always honours
            OptimizationConfig.plausibility.enabled).
    """
    prefix_to_region: dict[str, str] = field(default_factory=dict)
    region_to_macro: dict[str, str] = field(default_factory=dict)
    macro_to_label: dict[str, str] = field(default_factory=dict)

    # Candidate universe filter
    allowed_macro_regions: list[str] = field(default_factory=list)
    excluded_super_regions: list[str] = field(default_factory=list)
    excluded_regions: list[str] = field(default_factory=list)

    # Profile metadata flags
    profile_label: str = ""
    use_standard_mode: bool = True
    apply_plausibility_constraints: bool = True
    apply_remedy_passes: bool = True


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class MacroRegionGroup:
    macro_region: str
    percent: float
    label: str = ""     # optional ancestry-family label from macro_to_label


@dataclass
class GenericSummary:
    distance: float
    top_samples: list[dict]                # {name, percent} dicts, descending
    by_prefix: list[dict]                  # {region, percent} dicts, descending
    by_macro_region: list[MacroRegionGroup]
    summary_lines: list[str]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def aggregate_by_macro_region(
    aggregated: list[AggregatedPopulation],
    config: InterpretationConfig,
) -> list[MacroRegionGroup]:
    """
    Roll up prefix-level aggregates into macro-regions using config mappings.

    Fallback: unknown prefixes/regions pass through unchanged.

    Parameters
    ----------
    aggregated:
        Output of ``aggregate_by_prefix``.
    config:
        Interpretation configuration with mapping dicts.

    Returns
    -------
    list[MacroRegionGroup]
        One entry per distinct macro-region, sorted by percent descending.
    """
    totals: dict[str, float] = {}
    for agg in aggregated:
        region = config.prefix_to_region.get(agg.region, agg.region)
        macro = config.region_to_macro.get(region, region)
        totals[macro] = totals.get(macro, 0.0) + agg.percent

    return sorted(
        [
            MacroRegionGroup(
                macro_region=macro,
                percent=round(pct, 2),
                label=config.macro_to_label.get(macro, ""),
            )
            for macro, pct in totals.items()
        ],
        key=lambda g: g.percent,
        reverse=True,
    )


def build_generic_summary(
    result: RunResult,
    aggregated: list[AggregatedPopulation],
    config: InterpretationConfig,
) -> GenericSummary:
    """
    Build a fully generic, config-driven summary of a run result.

    All wording is derived from the actual computed data values — no
    target-specific text is ever hardcoded.

    Parameters
    ----------
    result:
        RunResult from the best iteration.
    aggregated:
        Prefix-level aggregates from ``aggregate_by_prefix``.
    config:
        Interpretation configuration.

    Returns
    -------
    GenericSummary
    """
    top_samples = [
        {"name": p.name, "percent": p.percent}
        for p in sorted(result.populations, key=lambda p: p.percent, reverse=True)
    ]

    by_prefix = [{"region": a.region, "percent": a.percent} for a in aggregated]

    by_macro = aggregate_by_macro_region(aggregated, config)

    summary_lines = _generate_summary_lines(result.distance, aggregated, by_macro)

    return GenericSummary(
        distance=result.distance,
        top_samples=top_samples,
        by_prefix=by_prefix,
        by_macro_region=by_macro,
        summary_lines=summary_lines,
    )


# ---------------------------------------------------------------------------
# Summary line generation (generic templates — no hardcoded ethnicity)
# ---------------------------------------------------------------------------

def _generate_summary_lines(
    distance: float,
    by_prefix: list[AggregatedPopulation],
    by_macro: list[MacroRegionGroup],
) -> list[str]:
    """
    Generate neutral, template-driven summary sentences from computed data.

    Sentence content is derived entirely from the input values; no
    target-specific names or ancestry labels are ever embedded in the code.
    """
    lines: list[str] = []

    # Sentence 1 — macro-region driver
    if by_macro:
        top_macros = [g.macro_region for g in by_macro[:2]]
        macro_str = (
            top_macros[0] if len(top_macros) == 1
            else f"{top_macros[0]} and {top_macros[1]}"
        )
        dominant_pct = sum(g.percent for g in by_macro[:2])
        lines.append(
            f"Best fit is driven mainly by {macro_str} proxies "
            f"({dominant_pct:.1f}% combined)."
        )

    # Sentence 2 — country-level summary
    if by_prefix:
        top4 = [a.region for a in by_prefix[:4]]
        if len(top4) == 1:
            country_str = top4[0]
        elif len(top4) == 2:
            country_str = f"{top4[0]} and {top4[1]}"
        else:
            country_str = ", ".join(top4[:-1]) + f", and {top4[-1]}"
        lines.append(
            f"Country-level aggregation shows strongest affinity to {country_str}."
        )

    # Sentence 3 — distance quality note
    if distance <= 0.02:
        quality = "very close fit"
    elif distance <= 0.03:
        quality = "close fit"
    elif distance <= 0.05:
        quality = "moderate fit"
    else:
        quality = "distant fit"
    lines.append(
        f"Best fit distance is {distance:.6f} ({quality})."
    )

    # Sentence 4 — standard methodological caveat
    lines.append(
        "These are proxy populations and should not be read as literal "
        "recent ethnic percentages."
    )

    return lines
