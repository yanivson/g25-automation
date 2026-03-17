"""
optimizer/scoring.py — classify population results into action categories.

Takes a RunResult and config thresholds and produces a PanelClassification
that tells the iteration manager what to do with each population.

All decisions are numeric-threshold-based and fully deterministic.
No LLM involvement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.result_parser import PopulationResult, RunResult


@dataclass
class OptimizationConfig:
    """Optimization thresholds (loaded from config.yaml optimization section)."""
    max_iterations: int
    stop_distance: float
    remove_percent_below: float
    strong_percent_at_or_above: float
    max_sources_per_panel: int
    max_initial_panel_size: int
    # Streak-based stop conditions (0 = disabled)
    stop_if_no_improvement_iterations: int = 0
    stop_if_panel_repeats: int = 0
    stop_if_all_new_candidates_zero: int = 0
    # Initial panel seeding strategy
    initial_panel_strategy: str = "alphabetical"   # alphabetical | nearest_by_distance | stratified_macro
    nearest_seed_count: int | None = None           # overrides max_initial_panel_size when set


@dataclass
class PanelClassification:
    """
    Classification of each population in the current panel result.

    strong:    percent >= strong_percent_at_or_above — always preserved
    surviving: remove_percent_below <= percent < strong_percent_at_or_above — kept for now
    weak:      percent < remove_percent_below (and not strong) — to be removed
    """
    strong: list[str] = field(default_factory=list)
    surviving: list[str] = field(default_factory=list)
    weak: list[str] = field(default_factory=list)

    @property
    def keep(self) -> list[str]:
        """All populations to retain in the next panel (strong + surviving)."""
        return self.strong + self.surviving

    @property
    def remove(self) -> list[str]:
        """All populations to drop and add to exhausted_set."""
        return self.weak


def classify_result(
    result: RunResult,
    config: OptimizationConfig,
) -> PanelClassification:
    """
    Classify each population in *result* into strong / surviving / weak.

    Classification rules:
      - strong:    percent >= config.strong_percent_at_or_above
      - weak:      percent < config.remove_percent_below  (and not strong)
      - surviving: everything else

    Strong status takes precedence: a population that meets the strong threshold
    is never classified as weak, even if remove_percent_below > strong_percent_at_or_above
    (which would be a misconfiguration, but handled safely).

    Parameters
    ----------
    result:
        Parsed RunResult from the most recent engine run.
    config:
        Optimization configuration thresholds.

    Returns
    -------
    PanelClassification
    """
    classification = PanelClassification()

    for pop in result.populations:
        if pop.percent >= config.strong_percent_at_or_above:
            classification.strong.append(pop.name)
        elif pop.percent < config.remove_percent_below:
            classification.weak.append(pop.name)
        else:
            classification.surviving.append(pop.name)

    return classification


def should_stop(
    result: RunResult,
    iteration: int,
    config: OptimizationConfig,
    panel_unchanged: bool = False,
    pool_exhausted: bool = False,
    no_improvement_streak: int = 0,
    panel_repeat_streak: int = 0,
    zero_new_candidates_streak: int = 0,
) -> tuple[bool, str]:
    """
    Check all stop conditions for the iteration loop.

    Conditions (checked in priority order):
      1. distance <= stop_distance           — success threshold met
      2. panel_unchanged                     — converged, no change possible
      3. pool_exhausted                      — no more candidates available
      4. no_improvement_streak >= N          — best distance stalled for N iterations
      5. panel_repeat_streak >= N            — effective contributing panel unchanged N times
      6. zero_new_candidates_streak >= N     — new fills contributed 0% for N iterations
      7. iteration >= max_iterations         — hard limit reached

    Streak conditions (4–6) are disabled when the corresponding config threshold is 0.

    Parameters
    ----------
    result:
        Most recent run result.
    iteration:
        Current iteration index (1-based).
    config:
        Optimization configuration.
    panel_unchanged:
        True if the proposed next panel is identical to the current panel.
    pool_exhausted:
        True if the remaining candidate pool (after exhausted_set removal) is empty.
    no_improvement_streak:
        Number of consecutive iterations where best_distance did not decrease.
    panel_repeat_streak:
        Number of consecutive iterations where the effective contributing panel
        (set of nonzero-percent population names) was identical.
    zero_new_candidates_streak:
        Number of consecutive iterations where all newly added fill candidates
        returned 0% contribution.

    Returns
    -------
    tuple[bool, str]
        (should_stop, reason_string)
    """
    if result.distance <= config.stop_distance:
        return True, f"stop_distance reached ({result.distance:.8f} <= {config.stop_distance})"
    if panel_unchanged:
        return True, "panel converged — no change between iterations"
    if pool_exhausted:
        return True, "candidate pool exhausted — no more populations to try"
    n = config.stop_if_no_improvement_iterations
    if n and no_improvement_streak >= n:
        return True, (
            f"no_improvement_streak={no_improvement_streak} "
            f">= stop_if_no_improvement_iterations={n}"
        )
    n = config.stop_if_panel_repeats
    if n and panel_repeat_streak >= n:
        return True, (
            f"panel_repeat_streak={panel_repeat_streak} "
            f">= stop_if_panel_repeats={n}"
        )
    n = config.stop_if_all_new_candidates_zero
    if n and zero_new_candidates_streak >= n:
        return True, (
            f"zero_new_candidates_streak={zero_new_candidates_streak} "
            f">= stop_if_all_new_candidates_zero={n}"
        )
    if iteration >= config.max_iterations:
        return True, f"max_iterations reached ({config.max_iterations})"
    return False, ""
