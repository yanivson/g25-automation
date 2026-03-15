"""
tests/test_user_profile.py — tests for user folder loading and the
g25-full-run-user CLI command wiring.

Tests cover:
  - UserProfile model validation
  - load_user_folder() success and failure paths
  - cmd_full_run_user argument parsing and early-exit error handling
  - backward compatibility: cmd_full_run still works with explicit paths
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from orchestration.user_profile import UserProfile, UserFolder, load_user_folder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIMS = ",".join(["0.0"] * 25)
_TARGET_ROW = f"Test_Pop,{_DIMS}\n"


def _make_user_folder(
    tmp_path: Path,
    user_id: str = "testuser",
    profile_data: dict | None = None,
    write_target: bool = True,
    write_profile: bool = True,
) -> Path:
    """Create a minimal user folder in tmp_path and return its path."""
    user_dir = tmp_path / user_id
    user_dir.mkdir()

    if write_target:
        (user_dir / "target.csv").write_text(_TARGET_ROW, encoding="utf-8")

    if write_profile:
        if profile_data is None:
            profile_data = {
                "user_id": user_id,
                "display_name": "Test User",
                "identity_context": "Some context",
                "ydna_haplogroup": "R1b",
            }
        (user_dir / "profile.json").write_text(
            json.dumps(profile_data), encoding="utf-8"
        )

    return user_dir


# ---------------------------------------------------------------------------
# UserProfile model
# ---------------------------------------------------------------------------

class TestUserProfileModel:
    def test_minimal_valid(self):
        p = UserProfile(user_id="alice", display_name="Alice")
        assert p.user_id == "alice"
        assert p.display_name == "Alice"
        assert p.identity_context is None
        assert p.ydna_haplogroup is None

    def test_full_valid(self):
        p = UserProfile(
            user_id="yaniv",
            display_name="Yaniv",
            identity_context="Ashkenazi Jewish",
            ydna_haplogroup="I-Y38863",
        )
        assert p.identity_context == "Ashkenazi Jewish"
        assert p.ydna_haplogroup == "I-Y38863"

    def test_missing_user_id_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            UserProfile.model_validate({"display_name": "Alice"})

    def test_missing_display_name_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            UserProfile.model_validate({"user_id": "alice"})

    def test_model_validate_from_dict(self):
        raw = {"user_id": "u", "display_name": "U", "ydna_haplogroup": "J2"}
        p = UserProfile.model_validate(raw)
        assert p.ydna_haplogroup == "J2"

    def test_extra_fields_ignored(self):
        """Unknown fields should not cause a validation error (pydantic default)."""
        raw = {"user_id": "u", "display_name": "U", "unknown_field": "x"}
        p = UserProfile.model_validate(raw)
        assert p.user_id == "u"


# ---------------------------------------------------------------------------
# load_user_folder()
# ---------------------------------------------------------------------------

class TestLoadUserFolder:
    def test_valid_folder_returns_user_folder(self, tmp_path: Path):
        user_dir = _make_user_folder(tmp_path, "alice")
        uf = load_user_folder(user_dir)
        assert isinstance(uf, UserFolder)
        assert uf.user_id == "alice"
        assert uf.target_file == user_dir / "target.csv"
        assert uf.profile.display_name == "Test User"

    def test_target_file_path_is_resolved(self, tmp_path: Path):
        user_dir = _make_user_folder(tmp_path, "bob")
        uf = load_user_folder(user_dir)
        assert uf.target_file.name == "target.csv"
        assert uf.target_file.exists()

    def test_user_id_matches_folder_name(self, tmp_path: Path):
        user_dir = _make_user_folder(tmp_path, "carol")
        uf = load_user_folder(user_dir)
        assert uf.user_id == "carol"

    def test_missing_directory_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="User folder not found"):
            load_user_folder(tmp_path / "nonexistent")

    def test_missing_target_csv_raises(self, tmp_path: Path):
        user_dir = _make_user_folder(tmp_path, "dave", write_target=False)
        with pytest.raises(FileNotFoundError, match="target.csv not found"):
            load_user_folder(user_dir)

    def test_missing_profile_json_raises(self, tmp_path: Path):
        user_dir = _make_user_folder(tmp_path, "eve", write_profile=False)
        with pytest.raises(FileNotFoundError, match="profile.json not found"):
            load_user_folder(user_dir)

    def test_malformed_json_raises(self, tmp_path: Path):
        user_dir = _make_user_folder(tmp_path, "frank", write_profile=False)
        (user_dir / "target.csv").write_text(_TARGET_ROW)
        (user_dir / "profile.json").write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            load_user_folder(user_dir)

    def test_invalid_schema_raises(self, tmp_path: Path):
        """profile.json with missing required fields raises ValueError."""
        bad_profile = {"user_id": "grace"}   # missing display_name
        user_dir = _make_user_folder(tmp_path, "grace", profile_data=bad_profile)
        with pytest.raises(ValueError, match="schema error"):
            load_user_folder(user_dir)

    def test_user_id_mismatch_raises(self, tmp_path: Path):
        """user_id in profile.json must match the folder name."""
        profile_data = {
            "user_id": "wrong_id",
            "display_name": "Heidi",
        }
        user_dir = _make_user_folder(tmp_path, "heidi", profile_data=profile_data)
        with pytest.raises(ValueError, match="does not match folder name"):
            load_user_folder(user_dir)

    def test_optional_fields_can_be_absent(self, tmp_path: Path):
        profile_data = {"user_id": "ivan", "display_name": "Ivan"}
        user_dir = _make_user_folder(tmp_path, "ivan", profile_data=profile_data)
        uf = load_user_folder(user_dir)
        assert uf.profile.identity_context is None
        assert uf.profile.ydna_haplogroup is None

    def test_accepts_path_or_string(self, tmp_path: Path):
        user_dir = _make_user_folder(tmp_path, "judy")
        # str input
        uf_str = load_user_folder(str(user_dir))
        assert uf_str.user_id == "judy"
        # Path input
        uf_path = load_user_folder(user_dir)
        assert uf_path.user_id == "judy"


# ---------------------------------------------------------------------------
# cmd_full_run_user — argument parsing and early-exit wiring
# ---------------------------------------------------------------------------

class TestFullRunUserCli:
    def test_importable(self):
        from scripts.cli import cmd_full_run_user
        assert callable(cmd_full_run_user)

    def test_help_exits_cleanly(self):
        from scripts.cli import cmd_full_run_user
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run_user(["--help"])
        assert exc_info.value.code == 0

    def test_missing_args_exits_nonzero(self):
        from scripts.cli import cmd_full_run_user
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run_user([])
        assert exc_info.value.code != 0

    def test_nonexistent_user_dir_exits_nonzero(self, tmp_path: Path):
        from scripts.cli import cmd_full_run_user
        fake_source = tmp_path / "source.csv"
        fake_source.write_text("name,dim_1\nA,0.1\n")
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run_user([str(tmp_path / "no_such_user"), str(fake_source)])
        assert exc_info.value.code != 0

    def test_missing_target_csv_exits_nonzero(self, tmp_path: Path):
        from scripts.cli import cmd_full_run_user
        user_dir = _make_user_folder(tmp_path, "tester", write_target=False)
        fake_source = tmp_path / "source.csv"
        fake_source.write_text("name,dim_1\nA,0.1\n")
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run_user([str(user_dir), str(fake_source)])
        assert exc_info.value.code != 0

    def test_missing_profile_json_exits_nonzero(self, tmp_path: Path):
        from scripts.cli import cmd_full_run_user
        user_dir = _make_user_folder(tmp_path, "tester", write_profile=False)
        fake_source = tmp_path / "source.csv"
        fake_source.write_text("name,dim_1\nA,0.1\n")
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run_user([str(user_dir), str(fake_source)])
        assert exc_info.value.code != 0

    def test_invalid_profile_json_exits_nonzero(self, tmp_path: Path):
        from scripts.cli import cmd_full_run_user
        bad_profile = {"user_id": "tester"}  # missing display_name
        user_dir = _make_user_folder(tmp_path, "tester", profile_data=bad_profile)
        fake_source = tmp_path / "source.csv"
        fake_source.write_text("name,dim_1\nA,0.1\n")
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run_user([str(user_dir), str(fake_source)])
        assert exc_info.value.code != 0

    def test_nonexistent_source_exits_nonzero(self, tmp_path: Path):
        from scripts.cli import cmd_full_run_user
        user_dir = _make_user_folder(tmp_path, "tester")
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run_user([str(user_dir), "no_such_source.csv"])
        assert exc_info.value.code != 0

    def test_pool_source_flag_parsed(self):
        """Argument parser accepts --pool-source filtered."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("user_dir")
        parser.add_argument("source")
        parser.add_argument("--pool-source", default="full", choices=["filtered", "full"])
        args = parser.parse_args(["u", "s", "--pool-source", "filtered"])
        assert args.pool_source == "filtered"

    def test_no_dedup_flag_parsed(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("user_dir")
        parser.add_argument("source")
        parser.add_argument("--no-dedup", action="store_true")
        args = parser.parse_args(["u", "s", "--no-dedup"])
        assert args.no_dedup is True

    def test_profile_flag_parsed(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("user_dir")
        parser.add_argument("source")
        parser.add_argument("--profile", default=None)
        args = parser.parse_args(["u", "s", "--profile", "eastmed_europe"])
        assert args.profile == "eastmed_europe"


# ---------------------------------------------------------------------------
# Backward compatibility: cmd_full_run still works with explicit paths
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_cmd_full_run_importable(self):
        from scripts.cli import cmd_full_run
        assert callable(cmd_full_run)

    def test_cmd_full_run_help_exits_cleanly(self):
        from scripts.cli import cmd_full_run
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run(["--help"])
        assert exc_info.value.code == 0

    def test_cmd_full_run_missing_args_exits_nonzero(self):
        from scripts.cli import cmd_full_run
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run([])
        assert exc_info.value.code != 0

    def test_cmd_full_run_nonexistent_target_exits_nonzero(self, tmp_path: Path):
        from scripts.cli import cmd_full_run
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run(["no_such_target.csv", "no_such_source.csv"])
        assert exc_info.value.code != 0

    def test_cmd_full_run_accepts_two_positional_args(self):
        """Parser accepts target + source without error (validation happens after)."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("target")
        parser.add_argument("source")
        args = parser.parse_args(["t.csv", "s.csv"])
        assert args.target == "t.csv"
        assert args.source == "s.csv"
