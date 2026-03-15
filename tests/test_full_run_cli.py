"""
tests/test_full_run_cli.py — wiring tests for the g25-full-run CLI command.

Tests cover argument parsing and flag interactions only.
No engine, no Playwright, no file I/O beyond tiny stubs.
Optimizer logic is not tested here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Argument-parser extraction helper
# ---------------------------------------------------------------------------
# We replicate the parser definition here so we can test it without importing
# the full cli module (which has heavyweight side-effect imports at call time).

def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g25-full-run")
    parser.add_argument("target")
    parser.add_argument("source")
    parser.add_argument("--config", default=None)
    parser.add_argument("--profile", default=None, metavar="PROFILE_NAME")
    parser.add_argument("--no-dedup", action="store_true")
    parser.add_argument(
        "--pool-source", default="filtered", choices=["filtered", "full"]
    )
    parser.add_argument("--output-dir", default=None)
    return parser


def _parse(argv: list[str]) -> argparse.Namespace:
    return _make_parser().parse_args(argv)


# ---------------------------------------------------------------------------
# Positional arguments
# ---------------------------------------------------------------------------

class TestPositionalArgs:
    def test_target_captured(self):
        args = _parse(["target.csv", "source.csv"])
        assert args.target == "target.csv"

    def test_source_captured(self):
        args = _parse(["target.csv", "source.csv"])
        assert args.source == "source.csv"

    def test_missing_target_raises(self):
        with pytest.raises(SystemExit):
            _parse([])

    def test_missing_source_raises(self):
        with pytest.raises(SystemExit):
            _parse(["target.csv"])


# ---------------------------------------------------------------------------
# --profile flag
# ---------------------------------------------------------------------------

class TestProfileFlag:
    def test_profile_defaults_to_none(self):
        args = _parse(["t.csv", "s.csv"])
        assert args.profile is None

    def test_profile_flag_captured(self):
        args = _parse(["t.csv", "s.csv", "--profile", "eastmed_europe"])
        assert args.profile == "eastmed_europe"

    def test_profile_is_string(self):
        args = _parse(["t.csv", "s.csv", "--profile", "northwest_europe"])
        assert isinstance(args.profile, str)

    def test_profile_minimal(self):
        args = _parse(["t.csv", "s.csv", "--profile", "minimal"])
        assert args.profile == "minimal"


# ---------------------------------------------------------------------------
# --no-dedup flag
# ---------------------------------------------------------------------------

class TestNoDedupFlag:
    def test_no_dedup_defaults_to_false(self):
        args = _parse(["t.csv", "s.csv"])
        assert args.no_dedup is False

    def test_no_dedup_flag_sets_true(self):
        args = _parse(["t.csv", "s.csv", "--no-dedup"])
        assert args.no_dedup is True

    def test_no_dedup_is_boolean(self):
        args = _parse(["t.csv", "s.csv", "--no-dedup"])
        assert isinstance(args.no_dedup, bool)


# ---------------------------------------------------------------------------
# --pool-source flag
# ---------------------------------------------------------------------------

class TestPoolSourceFlag:
    def test_pool_source_defaults_to_filtered(self):
        args = _parse(["t.csv", "s.csv"])
        assert args.pool_source == "filtered"

    def test_pool_source_filtered(self):
        args = _parse(["t.csv", "s.csv", "--pool-source", "filtered"])
        assert args.pool_source == "filtered"

    def test_pool_source_full(self):
        args = _parse(["t.csv", "s.csv", "--pool-source", "full"])
        assert args.pool_source == "full"

    def test_pool_source_invalid_raises(self):
        with pytest.raises(SystemExit):
            _parse(["t.csv", "s.csv", "--pool-source", "invalid_value"])


# ---------------------------------------------------------------------------
# --output-dir flag
# ---------------------------------------------------------------------------

class TestOutputDirFlag:
    def test_output_dir_defaults_to_none(self):
        args = _parse(["t.csv", "s.csv"])
        assert args.output_dir is None

    def test_output_dir_captured(self):
        args = _parse(["t.csv", "s.csv", "--output-dir", "/tmp/myrun"])
        assert args.output_dir == "/tmp/myrun"

    def test_output_dir_is_string(self):
        args = _parse(["t.csv", "s.csv", "--output-dir", "some/path"])
        assert isinstance(args.output_dir, str)


# ---------------------------------------------------------------------------
# --config flag
# ---------------------------------------------------------------------------

class TestConfigFlag:
    def test_config_defaults_to_none(self):
        args = _parse(["t.csv", "s.csv"])
        assert args.config is None

    def test_config_flag_captured(self):
        args = _parse(["t.csv", "s.csv", "--config", "my_config.yaml"])
        assert args.config == "my_config.yaml"


# ---------------------------------------------------------------------------
# Flag combinations
# ---------------------------------------------------------------------------

class TestFlagCombinations:
    def test_all_flags_together(self):
        args = _parse([
            "target.csv", "source.csv",
            "--profile", "eastmed_europe",
            "--no-dedup",
            "--pool-source", "full",
            "--output-dir", "/data/out",
            "--config", "cfg.yaml",
        ])
        assert args.target == "target.csv"
        assert args.source == "source.csv"
        assert args.profile == "eastmed_europe"
        assert args.no_dedup is True
        assert args.pool_source == "full"
        assert args.output_dir == "/data/out"
        assert args.config == "cfg.yaml"

    def test_no_dedup_and_full_pool_compatible(self):
        args = _parse(["t.csv", "s.csv", "--no-dedup", "--pool-source", "full"])
        assert args.no_dedup is True
        assert args.pool_source == "full"

    def test_profile_and_no_dedup_compatible(self):
        args = _parse(["t.csv", "s.csv", "--profile", "minimal", "--no-dedup"])
        assert args.profile == "minimal"
        assert args.no_dedup is True


# ---------------------------------------------------------------------------
# cmd_full_run is importable and callable with --help
# ---------------------------------------------------------------------------

class TestFullRunImport:
    def test_cmd_full_run_is_importable(self):
        from scripts.cli import cmd_full_run
        assert callable(cmd_full_run)

    def test_help_exits_cleanly(self):
        from scripts.cli import cmd_full_run
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run(["--help"])
        assert exc_info.value.code == 0

    def test_missing_args_exits_with_error(self):
        from scripts.cli import cmd_full_run
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run([])
        assert exc_info.value.code != 0

    def test_nonexistent_target_exits_with_error(self, tmp_path: Path):
        from scripts.cli import cmd_full_run
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run([
                "nonexistent_target.csv",
                "nonexistent_source.csv",
            ])
        assert exc_info.value.code != 0

    def test_nonexistent_source_exits_with_error(self, tmp_path: Path):
        from scripts.cli import cmd_full_run
        target = tmp_path / "target.csv"
        target.write_text("name,dim_1\nT,0.1\n")
        with pytest.raises(SystemExit) as exc_info:
            cmd_full_run([str(target), "nonexistent_source.csv"])
        assert exc_info.value.code != 0
