"""
orchestration/user_profile.py — User folder loading and profile validation.

New canonical layout (data/users/<user_id>/input/):
  input/target.csv    — G25 coordinate file (one population row)
  input/profile.json  — interpretation context metadata

Backward-compatible fallback: if the input/ subdirectory does not exist,
both files are looked up directly under user_dir/ (legacy layout).

The profile holds static per-user context for interpretation only.
It is never modified by the pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    """
    Interpretation context for one user. Loaded from profile.json.

    Fields
    ------
    user_id:
        Canonical identifier. Must match the containing folder name.
    display_name:
        Human-readable name used in reports.
    identity_context:
        Optional free-text description of the user's self-reported ancestry
        or genetic identity context (e.g. "Ashkenazi Jewish").
        Reserved for Phase 4 interpretation — not read by the optimizer.
    ydna_haplogroup:
        Optional Y-DNA haplogroup string (e.g. "I-Y38863").
        Reserved for Phase 4 interpretation — not read by the optimizer.
    """

    user_id: str
    display_name: str
    identity_context: str | None = None
    ydna_haplogroup: str | None = None


# ---------------------------------------------------------------------------
# Resolved folder handle
# ---------------------------------------------------------------------------

@dataclass
class UserFolder:
    """Resolved paths and validated metadata for one user folder."""

    user_id: str
    user_dir: Path
    target_file: Path
    profile: UserProfile


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _resolve_user_file(user_dir: Path, filename: str) -> Path:
    """
    Resolve a user input file with new-layout-first, legacy fallback.

    Checks ``input/<filename>`` first (new canonical location).
    Falls back to ``<filename>`` directly under user_dir (legacy location).
    Returns the resolved path regardless of whether it exists; the caller
    checks existence.
    """
    primary = user_dir / "input" / filename
    if primary.exists():
        return primary
    return user_dir / filename


def load_user_folder(user_dir: Path | str) -> UserFolder:
    """
    Load and validate a user folder.

    Supports both the new layout (input/ subdirectory) and the legacy
    layout (files directly under user_dir/).  New layout takes precedence.

    Parameters
    ----------
    user_dir:
        Path to ``data/users/<user_id>/`` directory.

    Returns
    -------
    UserFolder
        Resolved paths and validated UserProfile.

    Raises
    ------
    FileNotFoundError
        If the directory, ``target.csv``, or ``profile.json`` is missing.
    ValueError
        If ``profile.json`` is not valid JSON, fails schema validation,
        or if ``user_id`` in the file does not match the folder name.
    """
    user_dir = Path(user_dir)

    if not user_dir.is_dir():
        raise FileNotFoundError(f"User folder not found: {user_dir}")

    user_id = user_dir.name

    target_file = _resolve_user_file(user_dir, "target.csv")
    if not target_file.exists():
        raise FileNotFoundError(
            f"target.csv not found in user folder: {user_dir}"
        )

    profile_file = _resolve_user_file(user_dir, "profile.json")
    if not profile_file.exists():
        raise FileNotFoundError(
            f"profile.json not found in user folder: {user_dir}"
        )

    try:
        raw = json.loads(profile_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"profile.json is not valid JSON ({profile_file}): {exc}") from exc

    try:
        profile = UserProfile.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(
            f"profile.json schema error ({profile_file}):\n{exc}"
        ) from exc

    if profile.user_id != user_id:
        raise ValueError(
            f"profile.json user_id '{profile.user_id}' does not match "
            f"folder name '{user_id}'"
        )

    return UserFolder(
        user_id=user_id,
        user_dir=user_dir,
        target_file=target_file,
        profile=profile,
    )
