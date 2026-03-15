"""
tests/test_user_metadata_propagation.py — Verify user metadata from profile.json
flows correctly into evidence_pack.json and final_report.json.

Tests:
  TestUserMetadataPropagation
    - direct: _run_interpretation_from_run_dir with user kwargs
    - integration: cmd_full_run_user end-to-end (cmd_full_run mocked)
    - negative: cmd_full_run (no user folder) produces null user fields
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PROFILE = {
    "user_id": "yaniv",
    "display_name": "Yaniv",
    "identity_context": "Ashkenazi Jewish",
    "ydna_haplogroup": "I-Y38863",
}

_EXPECTED_USER = {
    "user_id": "yaniv",
    "display_name": "Yaniv",
    "identity_context": "Ashkenazi Jewish",
    "ydna_haplogroup": "I-Y38863",
}


def _make_run_dir(parent: Path, run_id: str = "test_run_001") -> Path:
    """Create a minimal valid run directory with required JSON artifacts."""
    run_dir = parent / run_id
    run_dir.mkdir(parents=True)
    meta = {
        "run_id": run_id,
        "best_distance": 0.024,
        "profile": "eastmed_europe",
        "best_iteration": 1,
        "stop_reason": "panel_repeat_streak=2 >= stop_if_panel_repeats=2",
    }
    (run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    agg = {
        "by_country": [{"region": "Italy", "percent": 60.0}],
        "top_samples": [{"name": "ITA_Roman", "percent": 60.0}],
    }
    (run_dir / "aggregated_result.json").write_text(json.dumps(agg), encoding="utf-8")
    return run_dir


def _make_user_folder(base: Path) -> Path:
    """Create data/users/yaniv/ with target.csv and profile.json."""
    user_dir = base / "users" / "yaniv"
    user_dir.mkdir(parents=True)
    # 26-column target row (name + 25 dims)
    (user_dir / "target.csv").write_text(
        "yaniv," + ",".join(["0.1"] * 25) + "\n",
        encoding="utf-8",
    )
    (user_dir / "profile.json").write_text(
        json.dumps(_PROFILE), encoding="utf-8"
    )
    return user_dir


# ---------------------------------------------------------------------------
# TestUserMetadataPropagation
# ---------------------------------------------------------------------------

class TestUserMetadataPropagation:
    """
    Tests that user metadata from profile.json is written into
    evidence_pack.json and final_report.json.
    """

    # ------------------------------------------------------------------
    # Level 1: direct call to _run_interpretation_from_run_dir
    # ------------------------------------------------------------------

    def test_helper_writes_user_id(self, tmp_path):
        import scripts.cli as cli_module
        run_dir = _make_run_dir(tmp_path)
        cli_module._run_interpretation_from_run_dir(run_dir, **_EXPECTED_USER)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"]["user_id"] == "yaniv"

    def test_helper_writes_display_name(self, tmp_path):
        import scripts.cli as cli_module
        run_dir = _make_run_dir(tmp_path)
        cli_module._run_interpretation_from_run_dir(run_dir, **_EXPECTED_USER)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"]["display_name"] == "Yaniv"

    def test_helper_writes_identity_context(self, tmp_path):
        import scripts.cli as cli_module
        run_dir = _make_run_dir(tmp_path)
        cli_module._run_interpretation_from_run_dir(run_dir, **_EXPECTED_USER)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"]["identity_context"] == "Ashkenazi Jewish"

    def test_helper_writes_ydna_haplogroup(self, tmp_path):
        import scripts.cli as cli_module
        run_dir = _make_run_dir(tmp_path)
        cli_module._run_interpretation_from_run_dir(run_dir, **_EXPECTED_USER)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"]["ydna_haplogroup"] == "I-Y38863"

    def test_helper_evidence_pack_has_user_id(self, tmp_path):
        import scripts.cli as cli_module
        run_dir = _make_run_dir(tmp_path)
        cli_module._run_interpretation_from_run_dir(run_dir, **_EXPECTED_USER)
        ep = json.loads((run_dir / "evidence_pack.json").read_text(encoding="utf-8"))
        assert ep["user_id"] == "yaniv"

    def test_helper_evidence_pack_has_all_user_fields(self, tmp_path):
        import scripts.cli as cli_module
        run_dir = _make_run_dir(tmp_path)
        cli_module._run_interpretation_from_run_dir(run_dir, **_EXPECTED_USER)
        ep = json.loads((run_dir / "evidence_pack.json").read_text(encoding="utf-8"))
        assert ep["user_id"] == "yaniv"
        assert ep["display_name"] == "Yaniv"
        assert ep["identity_context"] == "Ashkenazi Jewish"
        assert ep["ydna_haplogroup"] == "I-Y38863"

    def test_helper_without_user_metadata_produces_null(self, tmp_path):
        """Without user kwargs, user fields must be null (not missing)."""
        import scripts.cli as cli_module
        run_dir = _make_run_dir(tmp_path)
        cli_module._run_interpretation_from_run_dir(run_dir)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"]["user_id"] is None
        assert data["user"]["display_name"] is None
        assert data["user"]["identity_context"] is None
        assert data["user"]["ydna_haplogroup"] is None

    # ------------------------------------------------------------------
    # Level 2: end-to-end through cmd_full_run_user (cmd_full_run mocked)
    # ------------------------------------------------------------------

    def _run_full_run_user_mocked(self, tmp_path, run_id="fake_run_001"):
        """
        Run cmd_full_run_user with cmd_full_run mocked.
        Returns the run_dir path so callers can inspect artifacts.
        """
        import scripts.cli as cli_module
        from scripts.cli import cmd_full_run_user

        user_dir = _make_user_folder(tmp_path)
        source_file = tmp_path / "source.csv"
        source_file.write_text(
            "pop," + ",".join(["0.1"] * 25) + "\n", encoding="utf-8"
        )

        # Create the fake run directory that cmd_full_run would have written
        runs_dir = tmp_path / "results" / "runs"
        run_dir = _make_run_dir(runs_dir, run_id)

        fake_config = MagicMock()
        fake_config.runs_dir = runs_dir

        with (
            patch.object(cli_module, "cmd_full_run"),
            patch.object(cli_module, "_find_latest_run", return_value=run_id),
            patch("orchestration.pipeline.load_config", return_value=fake_config),
        ):
            cmd_full_run_user([str(user_dir), str(source_file)])

        # After the layout change, cmd_full_run_user moves the run dir into
        # the user-centric tree: user_dir/analysis/runs/<run_id>
        return user_dir / "analysis" / "runs" / run_id

    def test_cmd_full_run_user_final_report_user_id(self, tmp_path):
        run_dir = self._run_full_run_user_mocked(tmp_path)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"]["user_id"] == "yaniv"

    def test_cmd_full_run_user_final_report_display_name(self, tmp_path):
        run_dir = self._run_full_run_user_mocked(tmp_path)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"]["display_name"] == "Yaniv"

    def test_cmd_full_run_user_final_report_identity_context(self, tmp_path):
        run_dir = self._run_full_run_user_mocked(tmp_path)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"]["identity_context"] == "Ashkenazi Jewish"

    def test_cmd_full_run_user_final_report_ydna(self, tmp_path):
        run_dir = self._run_full_run_user_mocked(tmp_path)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"]["ydna_haplogroup"] == "I-Y38863"

    def test_cmd_full_run_user_evidence_pack_user_id(self, tmp_path):
        run_dir = self._run_full_run_user_mocked(tmp_path)
        ep = json.loads((run_dir / "evidence_pack.json").read_text(encoding="utf-8"))
        assert ep["user_id"] == "yaniv"

    def test_cmd_full_run_user_evidence_pack_all_fields(self, tmp_path):
        run_dir = self._run_full_run_user_mocked(tmp_path)
        ep = json.loads((run_dir / "evidence_pack.json").read_text(encoding="utf-8"))
        assert ep["user_id"] == "yaniv"
        assert ep["display_name"] == "Yaniv"
        assert ep["identity_context"] == "Ashkenazi Jewish"
        assert ep["ydna_haplogroup"] == "I-Y38863"

    def test_cmd_full_run_user_no_null_user_fields(self, tmp_path):
        """When profile.json is present, no user field in final_report may be null."""
        run_dir = self._run_full_run_user_mocked(tmp_path)
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        u = data["user"]
        assert None not in (u["user_id"], u["display_name"],
                            u["identity_context"], u["ydna_haplogroup"])

    def test_both_artifacts_agree_on_user_metadata(self, tmp_path):
        """evidence_pack.json and final_report.json must carry the same user values."""
        run_dir = self._run_full_run_user_mocked(tmp_path)
        ep = json.loads((run_dir / "evidence_pack.json").read_text(encoding="utf-8"))
        fr = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert fr["user"]["user_id"] == ep["user_id"]
        assert fr["user"]["display_name"] == ep["display_name"]
        assert fr["user"]["identity_context"] == ep["identity_context"]
        assert fr["user"]["ydna_haplogroup"] == ep["ydna_haplogroup"]

    # ------------------------------------------------------------------
    # Negative: cmd_full_run (no user folder) → null user fields
    # ------------------------------------------------------------------

    def test_cmd_full_run_user_fields_are_null_without_user_folder(self, tmp_path):
        """
        When the pipeline is run without a user folder (cmd_full_run),
        the user fields in final_report.json must be null.
        """
        run_dir = _make_run_dir(tmp_path)
        import scripts.cli as cli_module
        cli_module._run_interpretation_from_run_dir(run_dir)  # no user kwargs
        data = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
        assert data["user"] == {
            "user_id": None,
            "display_name": None,
            "identity_context": None,
            "ydna_haplogroup": None,
        }
