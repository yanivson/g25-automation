"""
orchestration/user_layout.py — User-centric folder layout.

Defines all paths for the user folder structure and provides
pure, idempotent operations for managing it.

Layout
------
data/users/<user_id>/
  input/
    target.csv
    profile.json
  analysis/
    runs/
      <run_id>/           full optimizer artifact bundle
    latest/               promoted subset of most recent run
  interpretation/
    interpretation.txt    hand-written; created once, never overwritten
  report/                 reserved for make_report output
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Files always promoted to latest/
# ---------------------------------------------------------------------------

_LATEST_ALWAYS: tuple[str, ...] = (
    "final_report.json",
    "evidence_pack.json",
    "best_result.json",
    "aggregated_result.json",
    "interpretation_status.json",
)

# Files promoted only when present in the run dir
_LATEST_OPTIONAL: tuple[str, ...] = (
    "generic_summary.json",
    "period_comparison.json",
)

_INTERPRETATION_STUB = "# Add your interpretation notes here\n"


# ---------------------------------------------------------------------------
# Layout dataclass — all paths derived from user_dir
# ---------------------------------------------------------------------------

@dataclass
class UserLayout:
    """All canonical paths for one user's folder tree."""

    user_dir: Path

    # -- input -----------------------------------------------------------------

    @property
    def input_dir(self) -> Path:
        return self.user_dir / "input"

    @property
    def target_file(self) -> Path:
        return self.input_dir / "target.csv"

    @property
    def profile_file(self) -> Path:
        return self.input_dir / "profile.json"

    # -- analysis --------------------------------------------------------------

    @property
    def analysis_dir(self) -> Path:
        return self.user_dir / "analysis"

    @property
    def runs_dir(self) -> Path:
        return self.analysis_dir / "runs"

    @property
    def latest_dir(self) -> Path:
        return self.analysis_dir / "latest"

    # -- interpretation --------------------------------------------------------

    @property
    def interpretation_dir(self) -> Path:
        return self.user_dir / "interpretation"

    @property
    def interpretation_txt(self) -> Path:
        return self.interpretation_dir / "interpretation.txt"

    # -- report ----------------------------------------------------------------

    @property
    def report_dir(self) -> Path:
        return self.user_dir / "report"


# ---------------------------------------------------------------------------
# Operations — all idempotent
# ---------------------------------------------------------------------------

def ensure_user_dirs(layout: UserLayout) -> None:
    """
    Create all required user subdirectories.

    Idempotent — safe to call before every run. Does not touch any files.
    """
    for d in (
        layout.input_dir,
        layout.runs_dir,
        layout.latest_dir,
        layout.interpretation_dir,
        layout.report_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)


def promote_to_latest(run_dir: Path, layout: UserLayout) -> list[str]:
    """
    Copy a fixed artifact subset from run_dir into analysis/latest/.

    Always copies the files in ``_LATEST_ALWAYS`` (if they exist).
    Copies ``_LATEST_OPTIONAL`` files only when present in run_dir.
    Overwrites any previous contents of latest/ — it always reflects
    the most recent run.

    Parameters
    ----------
    run_dir:
        Source run artifact directory.
    layout:
        UserLayout for the current user.

    Returns
    -------
    list[str]
        Names of files actually copied.
    """
    dest = layout.latest_dir
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in _LATEST_ALWAYS + _LATEST_OPTIONAL:
        src = run_dir / name
        if src.exists():
            shutil.copy2(src, dest / name)
            copied.append(name)
    return copied


def ensure_interpretation_stub(layout: UserLayout) -> bool:
    """
    Create interpretation/interpretation.txt if it does not exist.

    Never overwrites an existing file — preserves any hand-written content.

    Returns
    -------
    bool
        True if the file was created, False if it already existed.
    """
    txt = layout.interpretation_txt
    if txt.exists():
        return False
    txt.write_text(_INTERPRETATION_STUB, encoding="utf-8")
    return True
