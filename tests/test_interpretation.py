"""tests/test_interpretation.py — unit tests for optimizer/interpretation.py."""

from __future__ import annotations

import pytest

from engine.result_parser import PopulationResult, RunResult
from optimizer.aggregation import AggregatedPopulation, aggregate_by_prefix
from optimizer.interpretation import (
    InterpretationConfig,
    MacroRegionGroup,
    GenericSummary,
    aggregate_by_macro_region,
    build_generic_summary,
)


# ---------------------------------------------------------------------------
# Fixtures — two synthetic run profiles
# ---------------------------------------------------------------------------

def _east_med_config() -> InterpretationConfig:
    """Config appropriate for an East Mediterranean result."""
    return InterpretationConfig(
        prefix_to_region={
            "Israel": "Levant",
            "Lebanon": "Levant",
            "Turkey": "Anatolia",
            "Greece": "Southeastern Europe",
            "Italy": "Southern Europe",
        },
        region_to_macro={
            "Levant": "Eastern Mediterranean",
            "Anatolia": "Eastern Mediterranean",
            "Southeastern Europe": "Eastern Mediterranean",
            "Southern Europe": "Southern Europe",
        },
        macro_to_label={
            "Eastern Mediterranean": "East Mediterranean ancestry",
            "Southern Europe": "Southern European ancestry",
        },
    )


def _northwest_config() -> InterpretationConfig:
    """Config appropriate for a Northwestern European result."""
    return InterpretationConfig(
        prefix_to_region={
            "England": "Northwestern Europe",
            "Ireland": "Northwestern Europe",
            "Scotland": "Northwestern Europe",
            "Germany": "Central Europe",
            "France": "Western Europe",
            "Scandinavia": "Northwestern Europe",
        },
        region_to_macro={
            "Northwestern Europe": "Northwestern Europe",
            "Central Europe": "Central Europe",
            "Western Europe": "Western Europe",
        },
        macro_to_label={
            "Northwestern Europe": "Northwestern European ancestry",
            "Central Europe": "Central European ancestry",
            "Western Europe": "Western European ancestry",
        },
    )


def _result(distance: float, pops: list[tuple[str, float]]) -> RunResult:
    return RunResult(
        distance=distance,
        populations=[PopulationResult(name=n, percent=p) for n, p in pops],
        raw_output="<fake>",
    )


def _east_med_result() -> RunResult:
    return _result(0.025, [
        ("Israel_MLBA", 35.0),
        ("Turkey_Byzantine", 30.0),
        ("Greece_Classical", 20.0),
        ("Italy_Imperial", 15.0),
    ])


def _northwest_result() -> RunResult:
    return _result(0.018, [
        ("England_Roman", 40.0),
        ("Ireland_Medieval", 25.0),
        ("Germany_Medieval", 20.0),
        ("France_Medieval", 15.0),
    ])


def _east_med_aggregated() -> list[AggregatedPopulation]:
    return aggregate_by_prefix(_east_med_result())


def _northwest_aggregated() -> list[AggregatedPopulation]:
    return aggregate_by_prefix(_northwest_result())


# ---------------------------------------------------------------------------
# aggregate_by_macro_region
# ---------------------------------------------------------------------------

class TestAggregateByMacroRegion:
    def test_east_med_groups_into_eastern_mediterranean(self):
        agg = _east_med_aggregated()
        groups = aggregate_by_macro_region(agg, _east_med_config())
        macros = {g.macro_region: g.percent for g in groups}
        # Israel(35) -> Levant -> Eastern Med
        # Turkey(30) -> Anatolia -> Eastern Med
        # Greece(20) -> SE Europe -> Eastern Med
        assert "Eastern Mediterranean" in macros
        assert macros["Eastern Mediterranean"] == pytest.approx(85.0)

    def test_east_med_southern_europe_separate(self):
        agg = _east_med_aggregated()
        groups = aggregate_by_macro_region(agg, _east_med_config())
        macros = {g.macro_region: g.percent for g in groups}
        assert "Southern Europe" in macros
        assert macros["Southern Europe"] == pytest.approx(15.0)

    def test_northwest_splits_into_three_macros(self):
        agg = _northwest_aggregated()
        groups = aggregate_by_macro_region(agg, _northwest_config())
        macros = {g.macro_region for g in groups}
        assert "Northwestern Europe" in macros
        assert "Central Europe" in macros
        assert "Western Europe" in macros

    def test_northwest_percents_sum_to_100(self):
        agg = _northwest_aggregated()
        groups = aggregate_by_macro_region(agg, _northwest_config())
        total = sum(g.percent for g in groups)
        assert total == pytest.approx(100.0, abs=0.1)

    def test_sorted_descending_by_percent(self):
        agg = _east_med_aggregated()
        groups = aggregate_by_macro_region(agg, _east_med_config())
        percents = [g.percent for g in groups]
        assert percents == sorted(percents, reverse=True)

    def test_label_populated_from_config(self):
        agg = _east_med_aggregated()
        groups = aggregate_by_macro_region(agg, _east_med_config())
        by_macro = {g.macro_region: g.label for g in groups}
        assert by_macro["Eastern Mediterranean"] == "East Mediterranean ancestry"
        assert by_macro["Southern Europe"] == "Southern European ancestry"

    def test_unlisted_prefix_passes_through_as_region(self):
        """Population with no prefix_to_region mapping uses its prefix directly."""
        result = _result(0.05, [("Denmark_Ancient", 100.0)])
        agg = aggregate_by_prefix(result)
        config = InterpretationConfig()  # empty mappings
        groups = aggregate_by_macro_region(agg, config)
        assert groups[0].macro_region == "Denmark"

    def test_unlisted_region_passes_through_as_macro(self):
        """Region not in region_to_macro becomes its own macro-region."""
        result = _result(0.05, [("Denmark_Ancient", 100.0)])
        agg = aggregate_by_prefix(result)
        config = InterpretationConfig(
            prefix_to_region={"Denmark": "Scandinavia"},
        )
        groups = aggregate_by_macro_region(agg, config)
        assert groups[0].macro_region == "Scandinavia"

    def test_unlisted_macro_has_empty_label(self):
        """Macro-region not in macro_to_label gets empty string label."""
        result = _result(0.05, [("Denmark_Ancient", 100.0)])
        agg = aggregate_by_prefix(result)
        config = InterpretationConfig(
            prefix_to_region={"Denmark": "Scandinavia"},
            region_to_macro={"Scandinavia": "Nordic"},
        )
        groups = aggregate_by_macro_region(agg, config)
        assert groups[0].label == ""

    def test_empty_aggregated_returns_empty(self):
        groups = aggregate_by_macro_region([], _east_med_config())
        assert groups == []

    def test_returns_list_of_macro_region_group(self):
        agg = _east_med_aggregated()
        groups = aggregate_by_macro_region(agg, _east_med_config())
        assert all(isinstance(g, MacroRegionGroup) for g in groups)


# ---------------------------------------------------------------------------
# build_generic_summary
# ---------------------------------------------------------------------------

class TestBuildGenericSummary:
    def test_returns_generic_summary_instance(self):
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        assert isinstance(summary, GenericSummary)

    def test_distance_preserved(self):
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        assert summary.distance == pytest.approx(0.025)

    def test_top_samples_sorted_descending(self):
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        percents = [s["percent"] for s in summary.top_samples]
        assert percents == sorted(percents, reverse=True)

    def test_top_samples_have_name_and_percent(self):
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        for s in summary.top_samples:
            assert "name" in s
            assert "percent" in s

    def test_by_prefix_contains_region_and_percent(self):
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        for entry in summary.by_prefix:
            assert "region" in entry
            assert "percent" in entry

    def test_by_macro_region_is_list_of_macro_region_group(self):
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        assert all(isinstance(g, MacroRegionGroup) for g in summary.by_macro_region)

    def test_summary_lines_is_list_of_strings(self):
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        assert isinstance(summary.summary_lines, list)
        assert all(isinstance(line, str) for line in summary.summary_lines)

    def test_no_hardcoded_ethnicity_in_summary_lines_east_med(self):
        """Summary lines must not contain hardcoded ethnicity names."""
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        combined = " ".join(summary.summary_lines).lower()
        # None of these ethnic identity terms should appear as hardcoded strings
        for forbidden in ("jewish", "ashkenazi", "sephardic", "arab", "mediterranean person"):
            assert forbidden not in combined, (
                f"Hardcoded ethnicity term '{forbidden}' found in summary lines"
            )

    def test_no_hardcoded_ethnicity_in_summary_lines_northwest(self):
        """Summary lines must not contain hardcoded ethnicity names."""
        result = _northwest_result()
        agg = _northwest_aggregated()
        summary = build_generic_summary(result, agg, _northwest_config())
        combined = " ".join(summary.summary_lines).lower()
        for forbidden in ("british", "celtic", "anglo-saxon", "germanic person", "viking"):
            assert forbidden not in combined, (
                f"Hardcoded ethnicity term '{forbidden}' found in summary lines"
            )

    def test_east_med_summary_mentions_eastern_mediterranean(self):
        """The top macro-region name should appear in the first summary line."""
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        assert "Eastern Mediterranean" in summary.summary_lines[0]

    def test_northwest_summary_mentions_northwestern_europe(self):
        """The top macro-region name should appear in the first summary line."""
        result = _northwest_result()
        agg = _northwest_aggregated()
        summary = build_generic_summary(result, agg, _northwest_config())
        assert "Northwestern Europe" in summary.summary_lines[0]

    def test_distance_quality_close_fit(self):
        """Distance 0.025 should produce 'close fit' quality label."""
        result = _east_med_result()  # distance=0.025
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        distance_line = next(
            (l for l in summary.summary_lines if "distance" in l.lower()), ""
        )
        assert "close fit" in distance_line

    def test_distance_quality_very_close_fit(self):
        """Distance <= 0.02 should produce 'very close fit'."""
        result = _northwest_result()  # distance=0.018
        agg = _northwest_aggregated()
        summary = build_generic_summary(result, agg, _northwest_config())
        distance_line = next(
            (l for l in summary.summary_lines if "distance" in l.lower()), ""
        )
        assert "very close fit" in distance_line

    def test_summary_has_caveat_line(self):
        """Last summary line must contain the proxy-population caveat."""
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, _east_med_config())
        assert any("proxy" in line.lower() for line in summary.summary_lines)

    def test_empty_config_still_produces_output(self):
        """Empty InterpretationConfig must not raise — fallthrough applies."""
        result = _east_med_result()
        agg = _east_med_aggregated()
        summary = build_generic_summary(result, agg, InterpretationConfig())
        assert isinstance(summary, GenericSummary)
        assert len(summary.summary_lines) > 0
