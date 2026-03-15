"""
optimizer/panel_mutation.py — deterministic panel mutation rules.

Applies the classification from scoring.py to produce the next panel.

Rules (in order):
  1. Keep all strong + surviving populations from the current result.
  2. Add removed (weak) populations to the persistent exhausted_set.
  3. Count available slots: max_sources_per_panel - len(keep).
  4. Fill remaining slots from the candidate pool, excluding:
       - populations already in the keep set
       - populations in exhausted_set
     Candidates are drawn in sorted-name order (deterministic).
  5. Hard cap: final panel size <= max_sources_per_panel.

The exhausted_set grows monotonically — removed populations are never re-added.
All selection is by sorted name; no randomness is used anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from optimizer.scoring import OptimizationConfig, PanelClassification
from preprocessing.panel_builder import build_panel


@dataclass
class MutationState:
    """
    Persistent state carried across iterations.

    exhausted_set:
        Names of populations that have been removed at least once.
        Never re-introduced into the panel.
    candidate_pool_names:
        Sorted list of all names in the allowed candidate pool for this run.
        Fixed at the start of the iterative run; never modified.
    """
    exhausted_set: set[str] = field(default_factory=set)
    candidate_pool_names: list[str] = field(default_factory=list)

    def mark_exhausted(self, names: list[str]) -> None:
        """Add *names* to exhausted_set."""
        self.exhausted_set.update(names)

    @property
    def available_candidates(self) -> list[str]:
        """
        Sorted list of candidate pool names that have not yet been exhausted.
        Does not account for what is currently in the panel — callers subtract.
        """
        return [n for n in self.candidate_pool_names if n not in self.exhausted_set]

    def is_pool_exhausted(self, current_panel_names: set[str]) -> bool:
        """True if there are no unused candidates outside the current panel."""
        return not any(
            n for n in self.available_candidates if n not in current_panel_names
        )


def build_initial_panel_df(
    candidate_pool: pd.DataFrame,
    config: OptimizationConfig,
) -> pd.DataFrame:
    """
    Build the initial panel from the candidate pool.

    Strategy is controlled by ``config.initial_panel_strategy``:

    ``"alphabetical"`` (default):
        Sort pool by name, take the first *cap* rows.

    ``"nearest_by_distance"``:
        Assume *candidate_pool* is already sorted by ascending Euclidean
        distance to the target (done by the caller before this function is
        invoked). Take the first *cap* rows — no internal re-sorting.

    The size cap is ``config.nearest_seed_count`` if set, otherwise
    ``config.max_initial_panel_size``.

    Parameters
    ----------
    candidate_pool:
        Full candidate pool DataFrame. For ``nearest_by_distance`` strategy
        this must be pre-ranked by the caller.
    config:
        Optimization configuration.

    Returns
    -------
    pd.DataFrame
        Initial panel DataFrame, capped at the effective seed count.
    """
    cap = config.nearest_seed_count or config.max_initial_panel_size

    if config.initial_panel_strategy == "nearest_by_distance":
        pool = candidate_pool.reset_index(drop=True)
        label = "nearest_by_distance"
    else:
        pool = candidate_pool.sort_values("name").reset_index(drop=True)
        label = "sorted name"

    if len(pool) > cap:
        print(
            f"[panel_mutation] Candidate pool ({len(pool)}) exceeds "
            f"seed cap ({cap}). Using first {cap} by {label}."
        )
        pool = pool.iloc[:cap].reset_index(drop=True)
    return pool


@dataclass
class MutationResult:
    """Structured output from one apply_mutation() call."""
    next_panel_df: pd.DataFrame
    panel_unchanged: bool
    removed_names: list[str]   # populations dropped this iteration (= classification.weak)
    added_names: list[str]     # new fill candidates introduced this iteration


def apply_mutation(
    classification: PanelClassification,
    state: MutationState,
    candidate_pool_df: pd.DataFrame,
    config: OptimizationConfig,
) -> MutationResult:
    """
    Produce the next panel DataFrame by applying the mutation rules.

    Parameters
    ----------
    classification:
        Output of scoring.classify_result() for the most recent run.
    state:
        Persistent MutationState (exhausted_set is updated in-place).
    candidate_pool_df:
        Full candidate pool DataFrame (used to look up coordinates for new entries).
    config:
        Optimization configuration.

    Returns
    -------
    MutationResult
        Contains the next panel DataFrame, convergence flag, and the names
        of populations that were removed and added this iteration.
    """
    current_names: set[str] = set(classification.strong + classification.surviving + classification.weak)
    keep_names: list[str] = classification.keep  # strong + surviving, in result order

    # Step 1: mark weak populations as exhausted
    state.mark_exhausted(classification.weak)

    # Step 2: count available fill slots
    slots = config.max_sources_per_panel - len(keep_names)

    # Step 3: pick fill candidates — sorted by name, excluding kept and exhausted
    keep_name_set = set(keep_names)
    fill_candidates = [
        n for n in state.available_candidates
        if n not in keep_name_set
    ]
    selected_fill = fill_candidates[:max(0, slots)]

    # Step 4: build next name list (keep order: keep names first, then new fills)
    next_names = keep_names + selected_fill

    # Step 5: detect convergence
    panel_unchanged = set(next_names) == current_names

    # Step 6: look up rows from candidate_pool_df for all next_names
    next_panel_df = _lookup_rows(next_names, candidate_pool_df)

    return MutationResult(
        next_panel_df=next_panel_df,
        panel_unchanged=panel_unchanged,
        removed_names=list(classification.weak),
        added_names=selected_fill,
    )


def _lookup_rows(names: list[str], pool_df: pd.DataFrame) -> pd.DataFrame:
    """
    Return rows from *pool_df* in the order given by *names*.

    Populations in *names* that are not found in the pool are silently skipped
    (this should not happen in normal operation but is handled defensively).
    """
    idx_map = {row["name"]: i for i, row in pool_df.iterrows()}
    rows = [idx_map[n] for n in names if n in idx_map]
    return pool_df.loc[rows].reset_index(drop=True)


def panel_df_to_text(panel_df: pd.DataFrame) -> str:
    """Convert a panel DataFrame to the G25 text format expected by the engine."""
    return build_panel(panel_df)
