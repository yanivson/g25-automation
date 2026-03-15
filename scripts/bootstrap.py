"""
bootstrap.py — one-time project setup script.

Run with:
    python scripts/bootstrap.py

Actions:
  1. Clone (or update) the Vahaduo engine from GitHub into data/vahaduo_engine/
  2. Install the Playwright Chromium browser binary
  3. Print a verification checklist

This script is idempotent: re-running it will update the existing clone and
re-confirm the browser installation without destroying any existing data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a standalone script from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.setup import clone_or_update_vahaduo  # noqa: E402
from engine.inspector import inspect_vahaduo       # noqa: E402


def _install_playwright_browsers() -> None:
    """Install Chromium via the Playwright CLI."""
    import subprocess

    print("[bootstrap] Installing Playwright Chromium browser...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
    )
    if result.returncode != 0:
        print("[bootstrap] WARNING: playwright install exited with non-zero status.")
        print("            Run 'playwright install chromium' manually if needed.")
    else:
        print("[bootstrap] Playwright Chromium installed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap the G25 automation project (clone engine, install browsers)."
    )
    parser.add_argument(
        "--force-reclone",
        action="store_true",
        help="Delete and re-clone the Vahaduo engine even if it already exists.",
    )
    parser.add_argument(
        "--skip-inspect",
        action="store_true",
        help="Skip the post-clone code inspection step.",
    )
    args = parser.parse_args()

    engine_path = PROJECT_ROOT / "data" / "vahaduo_engine"

    # Step 1 — clone/update engine
    print("\n=== Step 1: Vahaduo engine ===")
    clone_or_update_vahaduo(engine_path, force=args.force_reclone)

    # Step 2 — install browsers
    print("\n=== Step 2: Playwright browsers ===")
    _install_playwright_browsers()

    # Step 3 — inspect cloned code
    if not args.skip_inspect:
        print("\n=== Step 3: Engine code inspection ===")
        inspection = inspect_vahaduo(engine_path)
        print(f"[bootstrap] Inspection complete. Report written to: {inspection.report_path}")
        print(f"[bootstrap] JS files found: {len(inspection.js_files)}")
        print(f"[bootstrap] Direct-function path available: {inspection.direct_function_available}")
    else:
        print("\n=== Step 3: Engine code inspection (skipped) ===")

    # Verification checklist
    print("\n=== Bootstrap complete ===")
    print("Checklist:")
    print(f"  [{'x' if engine_path.exists() else ' '}] data/vahaduo_engine/ exists")
    meta = engine_path / ".clone_meta.json"
    print(f"  [{'x' if meta.exists() else ' '}] .clone_meta.json written")
    inspection_file = engine_path / ".inspection.json"
    print(f"  [{'x' if inspection_file.exists() else ' '}] .inspection.json written")
    print()
    print("Next steps:")
    print("  1. Review data/vahaduo_engine/.inspection.json")
    print("  2. Implement engine/vahaduo_bridge.py using the inspection output")
    print("  3. Implement engine/result_parser.py based on the real output format")
    print("  4. Run: pytest tests/")


if __name__ == "__main__":
    main()
