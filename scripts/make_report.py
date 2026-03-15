"""
scripts/make_report.py — CLI shim.

All implementation lives in the ``report`` package.
This module exists solely for backwards-compatible imports
and as the registered setuptools entry point.
"""

from report.make_report import make_report, cmd_make_report  # noqa: F401
from report.templates import render_report  # noqa: F401

__all__ = ["make_report", "cmd_make_report", "render_report"]


if __name__ == "__main__":
    cmd_make_report()
