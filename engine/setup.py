"""
engine/setup.py — automated Vahaduo engine clone and update logic.

Called by scripts/bootstrap.py. Not a setuptools setup.py.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def clone_or_update_vahaduo(dest: Path, force: bool = False) -> None:
    """
    Clone vahaduo.github.io into *dest*, or update it if already present.

    Parameters
    ----------
    dest:
        Target directory for the engine clone.
    force:
        If True, delete *dest* and re-clone from scratch.
        If False (default), skip clone if a valid git repo already exists there,
        or run ``git pull`` to update it.

    Raises
    ------
    RuntimeError
        If *dest* exists but is not a valid git repository and *force* is False.
    """
    repo_url = "https://github.com/vahaduo/vahaduo"

    if dest.exists() and force:
        print(f"[engine/setup] --force-reclone: removing {dest}")
        import shutil
        shutil.rmtree(dest)

    if dest.exists():
        git_dir = dest / ".git"
        if not git_dir.is_dir():
            raise RuntimeError(
                f"{dest} exists but is not a git repository. "
                "Delete it manually or re-run with --force-reclone."
            )
        print(f"[engine/setup] Engine already cloned at {dest}. Pulling latest...")
        _run(["git", "-C", str(dest), "pull", "--ff-only"])
    else:
        print(f"[engine/setup] Cloning {repo_url} -> {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", repo_url, str(dest)])

    _write_clone_meta(dest, repo_url)


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n{result.stderr}"
        )


def _write_clone_meta(dest: Path, repo_url: str) -> None:
    """Write .clone_meta.json with commit SHA, timestamp, and remote URL."""
    result = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    commit_sha = result.stdout.strip() if result.returncode == 0 else "unknown"

    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit_sha": commit_sha,
        "remote_url": repo_url,
    }
    meta_path = dest / ".clone_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"[engine/setup] Clone meta written: commit={commit_sha[:8]}")
