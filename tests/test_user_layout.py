"""
tests/test_user_layout.py — Tests for orchestration/user_layout.py and
the updated user_profile.py fallback resolution.

Covers:
  TestUserLayoutPaths       — property derivation from user_dir
  TestEnsureUserDirs        — idempotent directory creation
  TestPromoteToLatest       — correct files copied, conditionals respected
  TestEnsureInterpretation  — create-once, no-overwrite
  TestEnsureReportDir       — covered by ensure_user_dirs; explicit check
  TestUserFolderFallback    — load_user_folder resolves new + legacy layouts
  TestCmdFullRunUserLayout  — end-to-end: run dir moved, latest/ populated
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestration.user_layout import (
    UserLayout,
    _INTERPRETATION_STUB,
    _LATEST_ALWAYS,
    _LATEST_OPTIONAL,
    ensure_interpretation_stub,
    ensure_user_dirs,
    promote_to_latest,
)
from orchestration.user_profile import load_user_folder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_layout(tmp_path: Path) -> UserLayout:
    user_dir = tmp_path / "users" / "yaniv"
    user_dir.mkdir(parents=True)
    return UserLayout(user_dir)


def _make_run_dir(parent: Path, run_id: str = "run_001") -> Path:
    run_dir = parent / run_id
    run_dir.mkdir(parents=True)
    for name in _LATEST_ALWAYS:
        (run_dir / name).write_text(f'{{"file": "{name}"}}', encoding="utf-8")
    return run_dir


def _make_user_folder_new(base: Path, user_id: str = "yaniv") -> Path:
    """New layout: files under input/."""
    user_dir = base / user_id
    (user_dir / "input").mkdir(parents=True)
    (user_dir / "input" / "target.csv").write_text(
        "yaniv," + ",".join(["0.1"] * 25) + "\n", encoding="utf-8"
    )
    (user_dir / "input" / "profile.json").write_text(
        json.dumps({"user_id": user_id, "display_name": "Yaniv"}), encoding="utf-8"
    )
    return user_dir


def _make_user_folder_legacy(base: Path, user_id: str = "yaniv") -> Path:
    """Legacy layout: files directly under user_dir/."""
    user_dir = base / user_id
    user_dir.mkdir(parents=True)
    (user_dir / "target.csv").write_text(
        "yaniv," + ",".join(["0.1"] * 25) + "\n", encoding="utf-8"
    )
    (user_dir / "profile.json").write_text(
        json.dumps({"user_id": user_id, "display_name": "Yaniv"}), encoding="utf-8"
    )
    return user_dir


# ---------------------------------------------------------------------------
# TestUserLayoutPaths
# ---------------------------------------------------------------------------

class TestUserLayoutPaths:
    def test_input_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        assert layout.input_dir == layout.user_dir / "input"

    def test_target_file(self, tmp_path):
        layout = _make_layout(tmp_path)
        assert layout.target_file == layout.user_dir / "input" / "target.csv"

    def test_profile_file(self, tmp_path):
        layout = _make_layout(tmp_path)
        assert layout.profile_file == layout.user_dir / "input" / "profile.json"

    def test_analysis_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        assert layout.analysis_dir == layout.user_dir / "analysis"

    def test_runs_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        assert layout.runs_dir == layout.user_dir / "analysis" / "runs"

    def test_latest_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        assert layout.latest_dir == layout.user_dir / "analysis" / "latest"

    def test_interpretation_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        assert layout.interpretation_dir == layout.user_dir / "interpretation"

    def test_interpretation_txt(self, tmp_path):
        layout = _make_layout(tmp_path)
        assert layout.interpretation_txt == layout.user_dir / "interpretation" / "interpretation.txt"

    def test_report_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        assert layout.report_dir == layout.user_dir / "report"


# ---------------------------------------------------------------------------
# TestEnsureUserDirs
# ---------------------------------------------------------------------------

class TestEnsureUserDirs:
    def test_creates_input_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        assert layout.input_dir.is_dir()

    def test_creates_runs_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        assert layout.runs_dir.is_dir()

    def test_creates_latest_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        assert layout.latest_dir.is_dir()

    def test_creates_interpretation_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        assert layout.interpretation_dir.is_dir()

    def test_creates_report_dir(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        assert layout.report_dir.is_dir()

    def test_idempotent(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        ensure_user_dirs(layout)  # must not raise
        assert layout.runs_dir.is_dir()

    def test_does_not_create_files(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        assert not list(layout.input_dir.iterdir())


# ---------------------------------------------------------------------------
# TestPromoteToLatest
# ---------------------------------------------------------------------------

class TestPromoteToLatest:
    def test_always_files_copied(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        run_dir = _make_run_dir(tmp_path)
        promote_to_latest(run_dir, layout)
        for name in _LATEST_ALWAYS:
            assert (layout.latest_dir / name).exists(), f"missing: {name}"

    def test_optional_files_copied_when_present(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        run_dir = _make_run_dir(tmp_path)
        for name in _LATEST_OPTIONAL:
            (run_dir / name).write_text("{}", encoding="utf-8")
        promoted = promote_to_latest(run_dir, layout)
        for name in _LATEST_OPTIONAL:
            assert (layout.latest_dir / name).exists()
            assert name in promoted

    def test_optional_files_not_copied_when_absent(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        run_dir = _make_run_dir(tmp_path)
        # No optional files in run_dir
        promote_to_latest(run_dir, layout)
        for name in _LATEST_OPTIONAL:
            assert not (layout.latest_dir / name).exists()

    def test_returns_list_of_copied_names(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        run_dir = _make_run_dir(tmp_path)
        copied = promote_to_latest(run_dir, layout)
        assert set(copied) == set(_LATEST_ALWAYS)

    def test_overwrites_previous_latest(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)

        run1 = _make_run_dir(tmp_path, "run_001")
        (run1 / "final_report.json").write_text('{"run": "001"}', encoding="utf-8")
        promote_to_latest(run1, layout)

        run2 = _make_run_dir(tmp_path, "run_002")
        (run2 / "final_report.json").write_text('{"run": "002"}', encoding="utf-8")
        promote_to_latest(run2, layout)

        data = json.loads(
            (layout.latest_dir / "final_report.json").read_text(encoding="utf-8")
        )
        assert data["run"] == "002"

    def test_skips_missing_always_files_gracefully(self, tmp_path):
        """If an always file is somehow absent, no error — just skip."""
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        run_dir = tmp_path / "empty_run"
        run_dir.mkdir()
        # No files at all
        copied = promote_to_latest(run_dir, layout)
        assert copied == []

    def test_creates_latest_dir_if_absent(self, tmp_path):
        layout = _make_layout(tmp_path)
        # Do NOT call ensure_user_dirs
        run_dir = _make_run_dir(tmp_path)
        promote_to_latest(run_dir, layout)
        assert layout.latest_dir.is_dir()


# ---------------------------------------------------------------------------
# TestEnsureInterpretation
# ---------------------------------------------------------------------------

class TestEnsureInterpretation:
    def test_creates_file_when_absent(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        result = ensure_interpretation_stub(layout)
        assert result is True
        assert layout.interpretation_txt.exists()

    def test_created_file_has_stub_content(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        ensure_interpretation_stub(layout)
        content = layout.interpretation_txt.read_text(encoding="utf-8")
        assert content == _INTERPRETATION_STUB

    def test_does_not_overwrite_existing(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        layout.interpretation_txt.write_text("My notes.\n", encoding="utf-8")
        result = ensure_interpretation_stub(layout)
        assert result is False
        assert layout.interpretation_txt.read_text(encoding="utf-8") == "My notes.\n"

    def test_returns_false_when_file_exists(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        layout.interpretation_txt.write_text("x", encoding="utf-8")
        assert ensure_interpretation_stub(layout) is False

    def test_idempotent_create(self, tmp_path):
        layout = _make_layout(tmp_path)
        ensure_user_dirs(layout)
        ensure_interpretation_stub(layout)
        ensure_interpretation_stub(layout)  # second call must not raise
        assert layout.interpretation_txt.read_text(encoding="utf-8") == _INTERPRETATION_STUB


# ---------------------------------------------------------------------------
# TestUserFolderFallback
# ---------------------------------------------------------------------------

class TestUserFolderFallback:
    def test_new_layout_reads_from_input(self, tmp_path):
        user_dir = _make_user_folder_new(tmp_path)
        uf = load_user_folder(user_dir)
        assert uf.target_file == user_dir / "input" / "target.csv"
        assert uf.profile.user_id == "yaniv"

    def test_legacy_layout_reads_from_root(self, tmp_path):
        user_dir = _make_user_folder_legacy(tmp_path)
        uf = load_user_folder(user_dir)
        assert uf.target_file == user_dir / "target.csv"
        assert uf.profile.user_id == "yaniv"

    def test_new_layout_preferred_over_legacy(self, tmp_path):
        """When both input/ and root-level files exist, input/ wins."""
        user_dir = _make_user_folder_new(tmp_path)
        # Also write legacy files with different content
        (user_dir / "target.csv").write_text("legacy", encoding="utf-8")
        (user_dir / "profile.json").write_text(
            json.dumps({"user_id": "yaniv", "display_name": "Legacy"}), encoding="utf-8"
        )
        uf = load_user_folder(user_dir)
        assert uf.target_file == user_dir / "input" / "target.csv"
        assert uf.profile.display_name == "Yaniv"  # from input/, not legacy

    def test_missing_target_raises(self, tmp_path):
        user_dir = tmp_path / "yaniv"
        user_dir.mkdir()
        (user_dir / "profile.json").write_text(
            json.dumps({"user_id": "yaniv", "display_name": "Yaniv"}), encoding="utf-8"
        )
        with pytest.raises(FileNotFoundError, match="target.csv"):
            load_user_folder(user_dir)

    def test_missing_profile_raises(self, tmp_path):
        user_dir = tmp_path / "yaniv"
        user_dir.mkdir()
        (user_dir / "target.csv").write_text("yaniv," + ",".join(["0.1"] * 25) + "\n")
        with pytest.raises(FileNotFoundError, match="profile.json"):
            load_user_folder(user_dir)


# ---------------------------------------------------------------------------
# TestCmdFullRunUserLayout
# ---------------------------------------------------------------------------

class TestCmdFullRunUserLayout:
    """
    End-to-end tests for the updated cmd_full_run_user:
    - run dir is moved to analysis/runs/<run_id>/
    - latest/ is populated
    - interpretation.txt is created
    - user metadata appears in both artifacts at the final location
    """

    def _setup(self, tmp_path: Path):
        """Return (user_dir, layout, source_file, runs_dir, run_dir)."""
        user_dir = _make_user_folder_new(tmp_path)
        source_file = tmp_path / "source.csv"
        source_file.write_text("pop," + ",".join(["0.1"] * 25) + "\n")

        # The "virtual" config.runs_dir where cmd_full_run writes
        config_runs_dir = tmp_path / "results" / "runs"

        # Pre-create a fake run dir that cmd_full_run would have produced
        run_id = "fake_run_001"
        run_dir = config_runs_dir / run_id
        run_dir.mkdir(parents=True)
        meta = {
            "run_id": run_id,
            "best_distance": 0.024,
            "profile": "eastmed_europe",
            "best_iteration": 1,
            "stop_reason": "panel_repeat_streak=2",
        }
        (run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        agg = {
            "by_country": [{"region": "Italy", "percent": 60.0}],
            "top_samples": [{"name": "ITA_Roman", "percent": 60.0}],
        }
        (run_dir / "aggregated_result.json").write_text(json.dumps(agg), encoding="utf-8")
        for name in _LATEST_ALWAYS:
            if not (run_dir / name).exists():
                (run_dir / name).write_text("{}", encoding="utf-8")

        layout = UserLayout(user_dir)
        fake_config = MagicMock()
        fake_config.runs_dir = config_runs_dir

        return user_dir, layout, source_file, fake_config, run_dir, run_id

    def _run_cmd(self, tmp_path, user_dir, source_file, fake_config, run_id):
        import scripts.cli as cli_module
        from scripts.cli import cmd_full_run_user
        with (
            patch.object(cli_module, "cmd_full_run"),
            patch.object(cli_module, "_find_latest_run", return_value=run_id),
            patch("orchestration.pipeline.load_config", return_value=fake_config),
        ):
            cmd_full_run_user([str(user_dir), str(source_file)])

    def test_run_dir_moved_to_user_analysis_runs(self, tmp_path):
        user_dir, layout, source, fake_config, _, run_id = self._setup(tmp_path)
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        assert (layout.runs_dir / run_id).is_dir()

    def test_run_dir_removed_from_config_runs_dir(self, tmp_path):
        user_dir, layout, source, fake_config, src_run_dir, run_id = self._setup(tmp_path)
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        assert not src_run_dir.exists()

    def test_latest_dir_populated(self, tmp_path):
        user_dir, layout, source, fake_config, _, run_id = self._setup(tmp_path)
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        assert layout.latest_dir.is_dir()
        assert any(layout.latest_dir.iterdir())

    def test_latest_has_final_report(self, tmp_path):
        user_dir, layout, source, fake_config, _, run_id = self._setup(tmp_path)
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        assert (layout.latest_dir / "final_report.json").exists()

    def test_latest_has_evidence_pack(self, tmp_path):
        user_dir, layout, source, fake_config, _, run_id = self._setup(tmp_path)
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        assert (layout.latest_dir / "evidence_pack.json").exists()

    def test_interpretation_txt_created(self, tmp_path):
        user_dir, layout, source, fake_config, _, run_id = self._setup(tmp_path)
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        assert layout.interpretation_txt.exists()

    def test_interpretation_txt_not_overwritten(self, tmp_path):
        user_dir, layout, source, fake_config, _, run_id = self._setup(tmp_path)
        layout.interpretation_dir.mkdir(parents=True, exist_ok=True)
        layout.interpretation_txt.write_text("My notes.\n", encoding="utf-8")
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        assert layout.interpretation_txt.read_text(encoding="utf-8") == "My notes.\n"

    def test_report_dir_created(self, tmp_path):
        user_dir, layout, source, fake_config, _, run_id = self._setup(tmp_path)
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        assert layout.report_dir.is_dir()

    def test_final_report_has_user_metadata(self, tmp_path):
        user_dir, layout, source, fake_config, _, run_id = self._setup(tmp_path)
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        final_report = layout.runs_dir / run_id / "final_report.json"
        data = json.loads(final_report.read_text(encoding="utf-8"))
        assert data["user"]["user_id"] == "yaniv"
        assert data["user"]["display_name"] == "Yaniv"

    def test_evidence_pack_has_user_metadata(self, tmp_path):
        user_dir, layout, source, fake_config, _, run_id = self._setup(tmp_path)
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        ep_path = layout.runs_dir / run_id / "evidence_pack.json"
        data = json.loads(ep_path.read_text(encoding="utf-8"))
        assert data["user_id"] == "yaniv"

    def test_latest_final_report_has_user_metadata(self, tmp_path):
        user_dir, layout, source, fake_config, _, run_id = self._setup(tmp_path)
        self._run_cmd(tmp_path, user_dir, source, fake_config, run_id)
        data = json.loads(
            (layout.latest_dir / "final_report.json").read_text(encoding="utf-8")
        )
        assert data["user"]["user_id"] == "yaniv"
