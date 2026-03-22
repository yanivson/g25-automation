"""
optimizer/plausibility.py — deterministic plausibility constraints for ancestry results.

Computes a composite score that combines raw Vahaduo fit distance with structural
penalties for known quality issues in genetic ancestry models.

Composite score formula:
    score = distance * drift_penalty * coherence_penalty * spread_penalty * substitute_penalty

All penalties are multiplicative factors >= 1.0.  A perfectly clean fit
(no drift-sensitive populations, coherent macro-region mix, no dust fragmentation,
no lone-outlier substitutes) yields composite_score == distance.

Used by iteration_manager.py to:
  - Select the best iteration by composite_score rather than raw distance.
  - Optionally use composite_score in the stop condition.

Enabled only in standard mode (plausibility_enabled=True in config).
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.result_parser import PopulationResult


# ---------------------------------------------------------------------------
# Drift-sensitive population prefixes
#
# These are highly isolated island or edge populations whose G25 coordinates
# are significantly skewed by extreme genetic drift.  When used as proxies they
# inject a systematic drift signal that inflates apparent ancestry percentages.
#
# Selection criteria:
#   - Small, isolated population with documented bottleneck / extreme drift
#   - G25 coordinates are visually displaced from continental neighbours
#   - Legitimate use cases exist (actual Faroese / Icelandic targets) but they
#     should not score equally well as a clean non-drift fit at the same distance
# ---------------------------------------------------------------------------

_DRIFT_SENSITIVE_PREFIXES: frozenset[str] = frozenset({
    "Faroes",
    "Faroe",       # alternate prefix in some datasets
    "Iceland",
    "Orkney",      # Scottish island isolate with Viking-age bottleneck
})


# ---------------------------------------------------------------------------
# PlausibilityConfig
# ---------------------------------------------------------------------------

@dataclass
class PlausibilityConfig:
    """
    Tuning parameters for the composite plausibility score.

    All penalty weights default to mild values so that the score stays close
    to the raw distance except in clearly problematic cases.
    """
    enabled: bool = True

    # ── Drift penalty ────────────────────────────────────────────────────────
    # penalty = 1 + (total_drift_fraction * drift_weight)
    # where total_drift_fraction = sum(% for drift-sensitive pops) / 100
    # Example: 30% Faroes → 1 + 0.30 * 0.30 = 1.09
    drift_weight: float = 0.30

    # ── Coherence penalty ────────────────────────────────────────────────────
    # Penalizes having too many distinct macro-regions contributing
    # significantly (> coherence_min_percent) to the ancestry model.
    # penalty = 1 + max(0, n_active_regions - coherence_max_regions) * per_extra
    coherence_max_regions: int = 5
    coherence_per_extra_region: float = 0.10
    coherence_min_percent: float = 3.0  # minimum % to count a region as active

    # ── Spread penalty (dust) ────────────────────────────────────────────────
    # Penalizes extreme fragmentation: many populations contributing < threshold%.
    # penalty = 1 + n_dust_pops * spread_per_dust
    spread_dust_threshold: float = 1.0
    spread_per_dust: float = 0.02

    # ── Substitute penalty (lone-outlier) ───────────────────────────────────
    # A population is a "lone outlier" if it:
    #   - contributes >= substitute_min_percent
    #   - is the sole representative of its macro-region
    #   - its macro-region is not among the top-2 by total contribution
    # penalty = 1 + n_lone_outliers * substitute_per_outlier
    substitute_min_percent: float = 5.0
    substitute_per_outlier: float = 0.10

    # ── Remedy pass ──────────────────────────────────────────────────────────
    # When the composite/distance ratio exceeds remedy_trigger_ratio, re-run
    # the engine with flagged populations removed from the panel.  If the
    # remedy result has a lower composite score, it replaces the original.
    remedy_enabled: bool = True
    # Ratio threshold to trigger a remedy pass (composite/distance)
    remedy_trigger_ratio: float = 1.15
    # Minimum drift-sensitive % contribution to include in remedy exclusion list
    remedy_drift_min_percent: float = 10.0

    # ── Lone substitute cleanup pass ─────────────────────────────────────────
    # Secondary pass run after the main remedy.  Detects macro-regions that
    # appear exactly once in the result AND whose total contribution is below
    # lone_substitute_threshold.  These are structural noise — sole, low-%
    # populations representing a distant macro-region — and are removed when
    # doing so does not materially worsen distance.
    #
    # Acceptance rule:  new_composite <= current_composite
    #                   AND new_distance - current_distance <= lone_sub_distance_tolerance
    lone_substitute_enabled: bool = True
    lone_substitute_threshold: float = 5.0   # max % to consider a macro-region as noise
    lone_substitute_distance_tolerance: float = 0.001  # max allowable distance increase

    # ── Low component cleanup pass ───────────────────────────────────────────
    # Tertiary pass run after the lone-substitute pass.  Catches residual tiny
    # contributions (< low_component_threshold, default 3%) that are the sole
    # representative of their macro-region and survived earlier passes because
    # they emerged from the new result after lone-sub removal.
    #
    # Isolation guard: a population is eligible ONLY if its macro-region appears
    # exactly once in the current result (same guard as lone-sub).  This prevents
    # removing valid small contributors that belong to a multi-member macro-cluster.
    #
    # Acceptance rule:  new_composite <= current_composite
    #                   AND new_distance - current_distance <= low_component_distance_tolerance
    low_component_enabled: bool = True
    low_component_threshold: float = 3.0    # max % for an isolated pop to be treated as noise
    low_component_distance_tolerance: float = 0.001  # max allowable distance increase


# ---------------------------------------------------------------------------
# Individual penalty functions
# ---------------------------------------------------------------------------

def compute_drift_penalty(
    populations: list[PopulationResult],
    config: PlausibilityConfig,
    drift_sensitive_prefixes: frozenset[str] = _DRIFT_SENSITIVE_PREFIXES,
) -> float:
    """
    Return the drift penalty factor (>= 1.0).

    Accumulates percent from drift-sensitive populations and applies a
    linear penalty proportional to that fraction.

    Parameters
    ----------
    populations:
        Contributing populations from the engine result.
    config:
        Plausibility configuration.
    drift_sensitive_prefixes:
        Set of name prefixes considered drift-sensitive.

    Returns
    -------
    float >= 1.0
    """
    total_drift = sum(
        p.percent
        for p in populations
        if p.name.split("_")[0] in drift_sensitive_prefixes
    )
    drift_fraction = total_drift / 100.0
    return 1.0 + drift_fraction * config.drift_weight


def compute_coherence_penalty(
    populations: list[PopulationResult],
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    config: PlausibilityConfig,
) -> float:
    """
    Return the coherence penalty factor (>= 1.0).

    Counts how many distinct canonical macro-regions contribute at least
    coherence_min_percent to the model.  Applies a per-extra-region penalty
    for each region above the allowed maximum.

    Parameters
    ----------
    populations:
        Contributing populations from the engine result.
    prefix_to_region / region_to_macro:
        Config metadata mappings (same as used for seeding).
    config:
        Plausibility configuration.

    Returns
    -------
    float >= 1.0
    """
    active_macros: set[str] = set()
    for pop in populations:
        if pop.percent < config.coherence_min_percent:
            continue
        prefix = pop.name.split("_")[0]
        region = prefix_to_region.get(prefix, prefix)
        macro = region_to_macro.get(region, region)
        active_macros.add(macro)

    n_extra = max(0, len(active_macros) - config.coherence_max_regions)
    return 1.0 + n_extra * config.coherence_per_extra_region


def compute_spread_penalty(
    populations: list[PopulationResult],
    config: PlausibilityConfig,
) -> float:
    """
    Return the spread (dust) penalty factor (>= 1.0).

    Counts how many populations contribute less than spread_dust_threshold%.
    Each such "dust" population adds a small penalty.

    Parameters
    ----------
    populations:
        Contributing populations from the engine result.
    config:
        Plausibility configuration.

    Returns
    -------
    float >= 1.0
    """
    n_dust = sum(
        1 for p in populations if p.percent < config.spread_dust_threshold
    )
    return 1.0 + n_dust * config.spread_per_dust


def compute_substitute_penalty(
    populations: list[PopulationResult],
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    config: PlausibilityConfig,
) -> float:
    """
    Return the substitute (lone-outlier) penalty factor (>= 1.0).

    A population is a "lone outlier" when:
      - its percent >= substitute_min_percent
      - it is the only representative of its macro-region in the result
      - its macro-region is not among the top-2 macro-regions by total %

    Such populations are likely acting as proxies for an ancestry component
    that the model cannot adequately represent from the available panel.

    Parameters
    ----------
    populations:
        Contributing populations from the engine result.
    prefix_to_region / region_to_macro:
        Config metadata mappings.
    config:
        Plausibility configuration.

    Returns
    -------
    float >= 1.0
    """
    if not prefix_to_region:
        return 1.0

    # Build per-macro totals and per-macro member list
    macro_total: dict[str, float] = {}
    macro_members: dict[str, list[str]] = {}
    for pop in populations:
        prefix = pop.name.split("_")[0]
        region = prefix_to_region.get(prefix, prefix)
        macro = region_to_macro.get(region, region)
        macro_total[macro] = macro_total.get(macro, 0.0) + pop.percent
        macro_members.setdefault(macro, []).append(pop.name)

    # Top-2 macro-regions by total contribution
    sorted_macros = sorted(macro_total, key=lambda m: macro_total[m], reverse=True)
    top2 = set(sorted_macros[:2])

    n_lone_outliers = 0
    for pop in populations:
        if pop.percent < config.substitute_min_percent:
            continue
        prefix = pop.name.split("_")[0]
        region = prefix_to_region.get(prefix, prefix)
        macro = region_to_macro.get(region, region)
        if macro not in top2 and len(macro_members.get(macro, [])) == 1:
            n_lone_outliers += 1

    return 1.0 + n_lone_outliers * config.substitute_per_outlier


# ---------------------------------------------------------------------------
# Remedy pass: identify populations to exclude
# ---------------------------------------------------------------------------

def identify_remedy_exclusions(
    populations: list[PopulationResult],
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    config: PlausibilityConfig,
    drift_sensitive_prefixes: frozenset[str] = _DRIFT_SENSITIVE_PREFIXES,
) -> set[str]:
    """
    Return names of populations that should be excluded in a remedy pass.

    Identifies two categories of structurally problematic populations:

    1. Drift-sensitive populations contributing >= remedy_drift_min_percent.
       Removing them gives the engine a chance to find a non-drift-inflated
       alternative that covers the same ancestry space.

    2. Lone-outlier substitutes: populations that contribute >=
       substitute_min_percent, are the sole representative of their
       macro-region, and whose macro-region is outside the top-2 by total %.
       These are likely proxying for a missing ancestry component.

    Parameters
    ----------
    populations:
        Contributing populations from the engine result (nonzero percent only
        is typical but the function handles any list).
    prefix_to_region / region_to_macro:
        Config metadata mappings.
    config:
        Plausibility configuration.
    drift_sensitive_prefixes:
        Set of name prefixes considered drift-sensitive.

    Returns
    -------
    set[str]
        Names of populations to remove from the panel before a remedy run.
        May be empty (no remedy needed for structural reasons).
    """
    to_exclude: set[str] = set()

    # ── Category 1: drift-sensitive contributors above remedy threshold ──────
    for pop in populations:
        prefix = pop.name.split("_")[0]
        if (
            prefix in drift_sensitive_prefixes
            and pop.percent >= config.remedy_drift_min_percent
        ):
            to_exclude.add(pop.name)

    # ── Category 2: lone-outlier substitutes ────────────────────────────────
    if prefix_to_region:
        macro_total: dict[str, float] = {}
        macro_members: dict[str, list[str]] = {}
        for pop in populations:
            prefix = pop.name.split("_")[0]
            region = prefix_to_region.get(prefix, prefix)
            macro = region_to_macro.get(region, region)
            macro_total[macro] = macro_total.get(macro, 0.0) + pop.percent
            macro_members.setdefault(macro, []).append(pop.name)

        sorted_macros = sorted(macro_total, key=lambda m: macro_total[m], reverse=True)
        top2 = set(sorted_macros[:2])

        for pop in populations:
            if pop.percent < config.substitute_min_percent:
                continue
            prefix = pop.name.split("_")[0]
            region = prefix_to_region.get(prefix, prefix)
            macro = region_to_macro.get(region, region)
            if macro not in top2 and len(macro_members.get(macro, [])) == 1:
                to_exclude.add(pop.name)

    return to_exclude


# ---------------------------------------------------------------------------
# Lone substitute detection (secondary cleanup pass)
# ---------------------------------------------------------------------------

def identify_lone_substitutes(
    populations: list[PopulationResult],
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
    threshold: float,
) -> set[str]:
    """
    Return names of populations that are structural noise: sole representatives
    of a macro-region whose total contribution is below ``threshold`` percent.

    Unlike the substitute_penalty logic (which targets high-% lone outliers
    outside the top-2 macro-regions), this function catches the opposite case:
    very small, isolated macro-region contributions that likely reflect noise
    rather than real ancestry.

    Detection criteria (both must hold):
      1. The population's canonical macro-region appears only once in the result.
      2. The total contribution from that macro-region is < threshold percent.

    No top-2 restriction — even small contributions to the top macro-regions
    are kept if they have multiple representatives.

    Parameters
    ----------
    populations:
        Contributing populations from the engine result.
    prefix_to_region / region_to_macro:
        Config metadata mappings.
    threshold:
        Maximum percent for a macro-region's total contribution to be
        considered a lone substitute (e.g. 5.0).

    Returns
    -------
    set[str]
        Names of lone-substitute populations to exclude.
        Empty set if no candidates are found or mappings are unavailable.
    """
    if not prefix_to_region:
        return set()

    macro_total: dict[str, float] = {}
    macro_members: dict[str, list[str]] = {}

    for pop in populations:
        prefix = pop.name.split("_")[0]
        region = prefix_to_region.get(prefix, prefix)
        macro = region_to_macro.get(region, region)
        macro_total[macro] = macro_total.get(macro, 0.0) + pop.percent
        macro_members.setdefault(macro, []).append(pop.name)

    to_exclude: set[str] = set()
    for macro, members in macro_members.items():
        if len(members) == 1 and macro_total.get(macro, 0.0) < threshold:
            to_exclude.add(members[0])

    return to_exclude


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

def compute_composite_score(
    distance: float,
    populations: list[PopulationResult],
    config: PlausibilityConfig,
    prefix_to_region: dict[str, str],
    region_to_macro: dict[str, str],
) -> tuple[float, dict[str, float]]:
    """
    Compute the composite plausibility score and all penalty components.

    score = distance * drift_penalty * coherence_penalty * spread_penalty
                     * substitute_penalty

    Parameters
    ----------
    distance:
        Raw Vahaduo fit distance from the engine result.
    populations:
        Contributing populations from the engine result.
    config:
        Plausibility configuration.
    prefix_to_region / region_to_macro:
        Config metadata mappings (may be empty dicts — gracefully degrades).

    Returns
    -------
    tuple[float, dict[str, float]]
        (composite_score, {penalty_name: value, ...})
        The dict contains all four individual penalty factors for logging.
    """
    if not config.enabled:
        return distance, {
            "drift_penalty": 1.0,
            "coherence_penalty": 1.0,
            "spread_penalty": 1.0,
            "substitute_penalty": 1.0,
        }

    dp = compute_drift_penalty(populations, config)
    cp = compute_coherence_penalty(populations, prefix_to_region, region_to_macro, config)
    sp = compute_spread_penalty(populations, config)
    scp = compute_substitute_penalty(populations, prefix_to_region, region_to_macro, config)

    score = distance * dp * cp * sp * scp

    return score, {
        "drift_penalty": dp,
        "coherence_penalty": cp,
        "spread_penalty": sp,
        "substitute_penalty": scp,
    }
