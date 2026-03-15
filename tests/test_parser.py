"""tests/test_parser.py — unit tests for engine/result_parser.py.

Uses real output format strings derived from confirmed singleFMC() HTML output
(github.com/vahaduo/vahaduo, inspected at commit dac51dff).
"""

from __future__ import annotations

import pytest

from engine.result_parser import parse_result, RunResult


# ---------------------------------------------------------------------------
# Fixture: canonical singleFMC HTML output
# ---------------------------------------------------------------------------

_SINGLE_RESULT_HTML = (
    "<table>"
    "<tr><th colspan='2' class='singleheader'>"
    "Target: Modern_Greek<br/>"
    "Distance: 1.2345% / 0.01234500<br/>"
    "<div class=\"singleinfo nonselectable\" "
    "data-nonselectable=\"Sources: 5 | Cycles: 2 | Time: 0.12 s\"></div>"
    "</th></tr>"
    "<tr><td class=\"singleleftcolumn\">42.1</td>"
    "<td class=\"singlerightcolumn\">Anatolia_Neolithic</td></tr>"
    "<tr><td class=\"singleleftcolumn\">28.3</td>"
    "<td class=\"singlerightcolumn\">Greece_Mycenaean</td></tr>"
    "<tr><td class=\"singleleftcolumn\">18.7</td>"
    "<td class=\"singlerightcolumn\">Levant_Bronze_Age</td></tr>"
    "<tr><td class=\"singleleftcolumn\">10.9</td>"
    "<td class=\"singlerightcolumn\">North_Africa_Berber</td></tr>"
    "</table>"
)

_MULTI_RESULT_HTML = (
    _SINGLE_RESULT_HTML
    + "<br><hr>"
    + "<table>"
    + "<tr><th colspan='2' class='singleheader'>"
    + "Target: Other_Sample<br/>"
    + "Distance: 2.5000% / 0.02500000<br/>"
    + "</th></tr>"
    + "<tr><td class=\"singleleftcolumn\">100.0</td>"
    + "<td class=\"singlerightcolumn\">Greece_Mycenaean</td></tr>"
    + "</table>"
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParseResult:
    def test_parse_valid_result_type(self):
        result = parse_result(_SINGLE_RESULT_HTML)
        assert isinstance(result, RunResult)

    def test_parse_distance(self):
        result = parse_result(_SINGLE_RESULT_HTML)
        assert abs(result.distance - 0.012345) < 1e-8

    def test_parse_populations_count(self):
        result = parse_result(_SINGLE_RESULT_HTML)
        assert len(result.populations) == 4

    def test_parse_population_names(self):
        result = parse_result(_SINGLE_RESULT_HTML)
        names = [p.name for p in result.populations]
        assert "Anatolia_Neolithic" in names
        assert "Greece_Mycenaean" in names

    def test_parse_population_percents(self):
        result = parse_result(_SINGLE_RESULT_HTML)
        top = result.populations[0]
        assert top.name == "Anatolia_Neolithic"
        assert abs(top.percent - 42.1) < 0.01

    def test_parse_raw_output_preserved(self):
        result = parse_result(_SINGLE_RESULT_HTML)
        assert result.raw_output == _SINGLE_RESULT_HTML

    def test_multi_result_uses_first_block_only(self):
        """When multiple results are stacked in #singleoutput, parse only the first."""
        result = parse_result(_MULTI_RESULT_HTML)
        assert abs(result.distance - 0.012345) < 1e-8
        assert len(result.populations) == 4

    def test_empty_output_raises(self):
        with pytest.raises(ValueError, match="Empty result"):
            parse_result("")

    def test_missing_distance_raises(self):
        bad_html = "<table><tr><td>no distance here</td></tr></table>"
        with pytest.raises(ValueError, match="distance"):
            parse_result(bad_html)

    def test_missing_populations_raises(self):
        no_pops = (
            "<table><tr><th>Target: X<br/>Distance: 0.5% / 0.00500000</th></tr></table>"
        )
        with pytest.raises(ValueError, match="population"):
            parse_result(no_pops)

    def test_distance_is_positive_float(self):
        result = parse_result(_SINGLE_RESULT_HTML)
        assert result.distance > 0
        assert isinstance(result.distance, float)

    def test_percents_sum_approximately_100(self):
        result = parse_result(_SINGLE_RESULT_HTML)
        total = sum(p.percent for p in result.populations)
        assert abs(total - 100.0) < 1.0  # small rounding tolerance
