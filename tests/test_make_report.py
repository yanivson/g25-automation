"""
tests/test_make_report.py — Tests for the HTML report generator.

Coverage:
  - make_report() creates report/report.html
  - HTML contains key user fields and section headings
  - Missing interpretation.txt handled gracefully
  - Missing period_comparison.json handled gracefully
  - Missing generic_summary.json handled gracefully
  - Bad user_dir raises FileNotFoundError
  - Missing analysis/latest/ raises FileNotFoundError
  - render_report() is deterministic (same inputs → same output)
  - cmd_make_report() CLI entry point smoke test
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.make_report import make_report, render_report


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_PROFILE = {
    "user_id": "testuser",
    "display_name": "Test User",
    "identity_context": "Test Context",
    "ydna_haplogroup": "R1b",
}

_FINAL_REPORT = {
    "user": {
        "user_id": "testuser",
        "display_name": "Test User",
        "identity_context": "Test Context",
        "ydna_haplogroup": "R1b",
    },
    "run": {
        "run_id": "run_001",
        "profile": "eastmed_europe",
        "best_distance": 0.024338,
        "distance_quality": "close fit",
        "best_iteration": 3,
        "stop_reason": "panel_repeat_streak=2",
    },
    "by_country": [
        {"region": "Italy",  "percent": 41.8},
        {"region": "Israel", "percent": 28.6},
    ],
    "by_macro_region": [
        {"macro_region": "Eastern Mediterranean", "percent": 58.2, "label": "East Med"},
        {"macro_region": "Southern Europe",       "percent": 41.8, "label": "S Europe"},
    ],
    "top_samples": [
        {"name": "Israel_MLBA_o",       "percent": 28.6},
        {"name": "Italy_Imperial_o1.SG","percent": 26.4},
    ],
    "periods": {"best_period": None, "comparison": []},
    "artifacts": {},
}

_AGGREGATED = {
    "distance": 0.024338,
    "by_country": _FINAL_REPORT["by_country"],
    "top_samples": _FINAL_REPORT["top_samples"],
}

_GENERIC_SUMMARY = {
    "profile": "eastmed_europe",
    "distance": 0.024338,
    "top_samples": _FINAL_REPORT["top_samples"],
    "by_prefix": _FINAL_REPORT["by_country"],
    "by_macro_region": _FINAL_REPORT["by_macro_region"],
    "summary_lines": ["Line one.", "Line two."],
}

_PERIOD_COMPARISON = {
    "periods": [
        {"period": "classical",    "distance": 0.031},
        {"period": "late_antiquity","distance": 0.025},
    ]
}

_INTERPRETATION = (
    "Historical Genetic Interpretation\n"
    "\n"
    "This is the first paragraph of genetic interpretation text covering primary ancestry.\n"
    "\n"
    "1. BRONZE AGE BACKGROUND\n"
    "\n"
    "This is the second paragraph covering additional genetic signals and population affinity.\n"
    "\n"
    "This third paragraph provides further detail and appears in the collapsible section.\n"
    "\n"
    "A fourth paragraph with supporting historical context, also in the collapsible section.\n"
)


def _make_user_dir(base: Path, with_interpretation: bool = True,
                   with_period: bool = True,
                   with_generic: bool = True) -> Path:
    user_dir = base / "users" / "testuser"

    # input/
    input_dir = user_dir / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "profile.json").write_text(json.dumps(_PROFILE), encoding="utf-8")

    # analysis/latest/
    latest = user_dir / "analysis" / "latest"
    latest.mkdir(parents=True)
    (latest / "final_report.json").write_text(json.dumps(_FINAL_REPORT), encoding="utf-8")
    (latest / "aggregated_result.json").write_text(json.dumps(_AGGREGATED), encoding="utf-8")
    if with_generic:
        (latest / "generic_summary.json").write_text(
            json.dumps(_GENERIC_SUMMARY), encoding="utf-8"
        )
    if with_period:
        (latest / "period_comparison.json").write_text(
            json.dumps(_PERIOD_COMPARISON), encoding="utf-8"
        )

    # interpretation/
    if with_interpretation:
        interp_dir = user_dir / "interpretation"
        interp_dir.mkdir(parents=True)
        (interp_dir / "interpretation.txt").write_text(
            _INTERPRETATION, encoding="utf-8"
        )

    return user_dir


# ---------------------------------------------------------------------------
# make_report() — file creation
# ---------------------------------------------------------------------------

class TestMakeReportFileCreation:
    def test_creates_report_dir(self, tmp_path):
        user_dir = _make_user_dir(tmp_path)
        make_report(user_dir)
        assert (user_dir / "report").is_dir()

    def test_creates_report_html(self, tmp_path):
        user_dir = _make_user_dir(tmp_path)
        output = make_report(user_dir)
        assert output.name == "report.html"
        assert output.exists()

    def test_returns_absolute_path(self, tmp_path):
        user_dir = _make_user_dir(tmp_path)
        output = make_report(user_dir)
        assert output.is_absolute()

    def test_output_under_report_dir(self, tmp_path):
        user_dir = _make_user_dir(tmp_path)
        output = make_report(user_dir)
        assert output.parent == (user_dir / "report").resolve()

    def test_idempotent_second_call(self, tmp_path):
        user_dir = _make_user_dir(tmp_path)
        make_report(user_dir)
        make_report(user_dir)  # must not raise
        assert (user_dir / "report" / "report.html").exists()

    def test_accepts_string_path(self, tmp_path):
        user_dir = _make_user_dir(tmp_path)
        output = make_report(str(user_dir))
        assert output.exists()


# ---------------------------------------------------------------------------
# HTML content — key fields present
# ---------------------------------------------------------------------------

class TestMakeReportHtmlContent:
    def _html(self, tmp_path, **kwargs) -> str:
        user_dir = _make_user_dir(tmp_path, **kwargs)
        output = make_report(user_dir)
        return output.read_text(encoding="utf-8")

    def test_contains_display_name(self, tmp_path):
        html = self._html(tmp_path)
        assert "Test User" in html

    def test_contains_distance(self, tmp_path):
        html = self._html(tmp_path)
        assert "0.024338" in html

    def test_contains_profile(self, tmp_path):
        html = self._html(tmp_path)
        assert "eastmed_europe" in html

    def test_contains_country_italy(self, tmp_path):
        html = self._html(tmp_path)
        assert "Italy" in html

    def test_contains_country_israel(self, tmp_path):
        html = self._html(tmp_path)
        assert "Israel" in html

    def test_contains_macro_region(self, tmp_path):
        html = self._html(tmp_path)
        assert "Eastern Mediterranean" in html

    def test_contains_sample_name(self, tmp_path):
        html = self._html(tmp_path)
        assert "Israel_MLBA_o" in html

    def test_contains_ydna(self, tmp_path):
        html = self._html(tmp_path)
        assert "R1b" in html

    def test_contains_identity_context(self, tmp_path):
        html = self._html(tmp_path)
        assert "Test Context" in html

    def test_contains_run_id(self, tmp_path):
        html = self._html(tmp_path)
        assert "run_001" in html

    def test_contains_interpretation_text(self, tmp_path):
        html = self._html(tmp_path)
        assert "Historical Genetic Interpretation" in html

    def test_is_valid_html_doctype(self, tmp_path):
        html = self._html(tmp_path)
        assert html.strip().startswith("<!DOCTYPE html>")

    def test_has_viewport_meta(self, tmp_path):
        html = self._html(tmp_path)
        assert 'name="viewport"' in html


# ---------------------------------------------------------------------------
# Section headings present
# ---------------------------------------------------------------------------

class TestSectionHeadings:
    def _html(self, tmp_path) -> str:
        user_dir = _make_user_dir(tmp_path)
        return make_report(user_dir).read_text(encoding="utf-8")

    def test_has_ancestry_section(self, tmp_path):
        assert "Ancestry Distribution" in self._html(tmp_path)

    def test_has_interpretation_section(self, tmp_path):
        assert "Historical Interpretation" in self._html(tmp_path)

    def test_has_period_section(self, tmp_path):
        # "Period Diagnostics" appears as the appendix subsection summary
        assert "Period Diagnostics" in self._html(tmp_path)

    def test_has_period_signal_card_when_data_present(self, tmp_path):
        assert "Historical Period Signal" in self._html(tmp_path)

    def test_has_samples_section(self, tmp_path):
        assert "Sample-Level Proxies" in self._html(tmp_path)

    def test_has_run_metadata_section(self, tmp_path):
        assert "Technical Appendix" in self._html(tmp_path)

    def test_has_key_genetic_signal(self, tmp_path):
        assert "Key Genetic Signal" in self._html(tmp_path)

    def test_key_signal_contains_primary_macro(self, tmp_path):
        html = self._html(tmp_path)
        assert "Eastern Mediterranean" in html
        assert "Primary signal" in html

    def test_key_signal_contains_top_country(self, tmp_path):
        html = self._html(tmp_path)
        assert "Strongest country proxy" in html
        assert "Italy" in html

    def test_key_signal_in_section_c_not_standalone(self, tmp_path):
        html = self._html(tmp_path)
        # Key Genetic Signal appears inside section C (interpretation), not as own section
        # Verify it is present and that Period Diagnostics is only in appendix
        assert "Key Genetic Signal" in html
        # There is no standalone "Period Diagnostics" section (only in <details> appendix)
        import re
        # section-title class should not contain "Period Diagnostics"
        assert 'class="section-title">Period Diagnostics' not in html

    def test_period_detail_only_in_appendix(self, tmp_path):
        html = self._html(tmp_path)
        # appendix-details class wraps the period detail — not a top-level section
        assert 'class="appendix-details"' in html


# ---------------------------------------------------------------------------
# Graceful handling of missing optional files
# ---------------------------------------------------------------------------

class TestMissingOptionalFiles:
    def test_missing_interpretation_txt_no_crash(self, tmp_path):
        user_dir = _make_user_dir(tmp_path, with_interpretation=False)
        output = make_report(user_dir)
        assert output.exists()

    def test_missing_interpretation_shows_placeholder(self, tmp_path):
        user_dir = _make_user_dir(tmp_path, with_interpretation=False)
        html = make_report(user_dir).read_text(encoding="utf-8")
        assert "interpretation.txt" in html  # placeholder references the file

    def test_missing_period_comparison_no_crash(self, tmp_path):
        user_dir = _make_user_dir(tmp_path, with_period=False)
        output = make_report(user_dir)
        assert output.exists()

    def test_missing_period_shows_no_data_message(self, tmp_path):
        user_dir = _make_user_dir(tmp_path, with_period=False)
        html = make_report(user_dir).read_text(encoding="utf-8")
        assert "not generated" in html

    def test_no_period_signal_card_when_no_data(self, tmp_path):
        # Compact card hidden when period data is missing
        user_dir = _make_user_dir(tmp_path, with_period=False)
        html = make_report(user_dir).read_text(encoding="utf-8")
        assert "Historical Period Signal" not in html
        # But appendix always shows the subsection header + no-data message
        assert "Period Diagnostics" in html
        assert "not generated" in html

    def test_period_signal_card_content_when_data_present(self, tmp_path):
        user_dir = _make_user_dir(tmp_path, with_period=True)
        html = make_report(user_dir).read_text(encoding="utf-8")
        assert "Historical Period Signal" in html
        assert "closest single-period approximation" in html
        assert "primary result" in html

    def test_missing_generic_summary_no_crash(self, tmp_path):
        user_dir = _make_user_dir(tmp_path, with_generic=False)
        output = make_report(user_dir)
        assert output.exists()


# ---------------------------------------------------------------------------
# Interpretation collapse / read-more
# ---------------------------------------------------------------------------

class TestInterpretationCollapse:
    def _html(self, tmp_path) -> str:
        user_dir = _make_user_dir(tmp_path)
        return make_report(user_dir).read_text(encoding="utf-8")

    def test_interpretation_content_preserved(self, tmp_path):
        html = self._html(tmp_path)
        assert "Historical Genetic Interpretation" in html
        assert "first paragraph" in html

    def test_interpretation_preview_container_present(self, tmp_path):
        html = self._html(tmp_path)
        assert 'interpretation-preview' in html

    def test_interpretation_hidden_container_present(self, tmp_path):
        html = self._html(tmp_path)
        assert 'interpretation-hidden' in html

    def test_interpretation_toggle_button_present(self, tmp_path):
        html = self._html(tmp_path)
        assert "Read full interpretation" in html

    def test_interpretation_toggle_aria_expanded_false_by_default(self, tmp_path):
        html = self._html(tmp_path)
        assert 'aria-expanded="false"' in html

    def test_third_paragraph_in_hidden_section(self, tmp_path):
        html = self._html(tmp_path)
        # Search by HTML attribute (not CSS class selector) to skip the style block
        hidden_start = html.find('class="interpretation-hidden"')
        assert hidden_start != -1
        assert "third paragraph" in html[hidden_start:]

    def test_first_paragraph_in_preview_section(self, tmp_path):
        html = self._html(tmp_path)
        preview_start = html.find('class="interpretation-preview"')
        hidden_start = html.find('class="interpretation-hidden"')
        assert preview_start != -1 and hidden_start != -1
        preview_section = html[preview_start:hidden_start]
        assert "first paragraph" in preview_section

    def test_no_collapse_when_interpretation_missing(self, tmp_path):
        user_dir = _make_user_dir(tmp_path, with_interpretation=False)
        html = make_report(user_dir).read_text(encoding="utf-8")
        # Check that the HTML button element is absent (JS may still contain the label string)
        assert 'class="interpretation-toggle"' not in html

    def test_hero_takeaway_present(self, tmp_path):
        html = self._html(tmp_path)
        assert "Closest overall fit" in html

    def test_hero_takeaway_contains_macro_regions(self, tmp_path):
        html = self._html(tmp_path)
        assert "Eastern Mediterranean" in html
        assert "Southern Europe" in html

    def test_interpretation_split_at_subsection_heading(self, tmp_path):
        html = self._html(tmp_path)
        # "Bronze Age Background" heading should appear in the hidden section
        hidden_start = html.find('class="interpretation-hidden"')
        assert hidden_start != -1
        assert "Bronze Age" in html[hidden_start:]

    def test_period_card_before_interpretation(self, tmp_path):
        html = self._html(tmp_path)
        period_pos = html.find("Historical Period Signal")
        preview_pos = html.find('class="interpretation-preview"')
        assert period_pos != -1 and preview_pos != -1
        assert period_pos < preview_pos, (
            "Period Signal card should appear before the interpretation preview"
        )


# ---------------------------------------------------------------------------
# Hero metric row
# ---------------------------------------------------------------------------

class TestHeroMetrics:
    def _html(self, tmp_path) -> str:
        user_dir = _make_user_dir(tmp_path)
        return make_report(user_dir).read_text(encoding="utf-8")

    def test_hero_metrics_row_present(self, tmp_path):
        html = self._html(tmp_path)
        assert "Strongest country proxy" in html

    def test_hero_metrics_top_country(self, tmp_path):
        html = self._html(tmp_path)
        # Italy is the top country (41.8%) — should appear in hero-metrics
        assert "41.8" in html

    def test_hero_metrics_fit_quality(self, tmp_path):
        html = self._html(tmp_path)
        assert "close fit" in html

    def test_hero_metrics_container_class(self, tmp_path):
        html = self._html(tmp_path)
        assert 'class="hero-metrics"' in html


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestMakeReportErrors:
    def test_missing_user_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            make_report(tmp_path / "nonexistent")

    def test_missing_latest_raises(self, tmp_path):
        user_dir = tmp_path / "users" / "u1"
        (user_dir / "input").mkdir(parents=True)
        (user_dir / "input" / "profile.json").write_text(
            json.dumps(_PROFILE), encoding="utf-8"
        )
        with pytest.raises(FileNotFoundError, match="analysis/latest"):
            make_report(user_dir)


# ---------------------------------------------------------------------------
# render_report() determinism
# ---------------------------------------------------------------------------

class TestRenderReportDeterminism:
    def _render(self) -> str:
        return render_report(
            profile=_PROFILE,
            final_report=_FINAL_REPORT,
            aggregated=_AGGREGATED,
            generic_summary=_GENERIC_SUMMARY,
            period_data=_PERIOD_COMPARISON,
            interpretation=_INTERPRETATION,
        )

    def test_deterministic(self):
        assert self._render() == self._render()

    def test_returns_string(self):
        assert isinstance(self._render(), str)

    def test_no_cdn_references(self):
        html = self._render()
        for cdn in ("cdn.jsdelivr.net", "cdnjs", "googleapis.com", "unpkg.com"):
            assert cdn not in html, f"CDN reference found: {cdn}"

    def test_no_external_scripts(self):
        html = self._render()
        assert 'src="http' not in html
        assert "src='http" not in html


# ---------------------------------------------------------------------------
# cmd_make_report CLI smoke test
# ---------------------------------------------------------------------------

class TestCmdMakeReport:
    def test_cli_creates_html(self, tmp_path):
        from scripts.make_report import cmd_make_report
        user_dir = _make_user_dir(tmp_path)
        cmd_make_report([str(user_dir)])
        assert (user_dir / "report" / "report.html").exists()

    def test_cli_missing_dir_exits_nonzero(self, tmp_path):
        from scripts.make_report import cmd_make_report
        with pytest.raises(SystemExit) as exc_info:
            cmd_make_report([str(tmp_path / "no_such_dir")])
        assert exc_info.value.code != 0
