"""
optimizer/aggregation.py — post-processing aggregation by geographic prefix.

Groups populations by the first underscore-delimited token in their name and
sums their percentages. Pure post-processing; no optimizer logic is touched.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.result_parser import RunResult


@dataclass
class AggregatedPopulation:
    region: str
    percent: float


def aggregate_by_prefix(result: RunResult) -> list[AggregatedPopulation]:
    """
    Sum population percentages by the first ``_``-delimited token in each name.

    Parameters
    ----------
    result:
        Parsed RunResult from any iteration.

    Returns
    -------
    list[AggregatedPopulation]
        One entry per unique prefix, sorted by percent descending.
    """
    totals: dict[str, float] = {}
    for pop in result.populations:
        prefix = pop.name.split("_")[0]
        totals[prefix] = totals.get(prefix, 0.0) + pop.percent

    return sorted(
        [AggregatedPopulation(region=k, percent=round(v, 2)) for k, v in totals.items()],
        key=lambda a: a.percent,
        reverse=True,
    )
