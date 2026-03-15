"""
engine/playwright_runner.py — Playwright context and page lifecycle.

Opens a headless Chromium browser, navigates to the local Vahaduo page,
and delegates all JS interaction to VahaduoBridge.

This module must not contain any selector strings or JS snippets — those
belong exclusively in vahaduo_bridge.py.
"""

from __future__ import annotations

from engine.vahaduo_bridge import VahaduoBridge


def run_vahaduo(
    url: str,
    panel_text: str,
    target_text: str,
    bridge: VahaduoBridge | None = None,
) -> str:
    """
    Open the local Vahaduo page, inject panel + target, run the model, and
    return the raw result string.

    Parameters
    ----------
    url:
        Base URL of the locally-served Vahaduo page
        (e.g. ``"http://localhost:54321"``).
    panel_text:
        G25 source panel string (from panel_builder.build_panel()).
    target_text:
        G25 target row string (single-population panel-format string).
    bridge:
        VahaduoBridge instance to use. Defaults to a new VahaduoBridge().

    Returns
    -------
    str
        Raw result text extracted by bridge.extract_result().

    Raises
    ------
    NotImplementedError
        Until VahaduoBridge methods are implemented after engine inspection.
    RuntimeError
        If the page fails to load or the result cannot be extracted.
    """
    from playwright.sync_api import sync_playwright

    if bridge is None:
        bridge = VahaduoBridge()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()

            # Navigate and wait until the inline JS has executed.
            # "domcontentloaded" is sufficient — the app has no external JS
            # dependencies; all logic is inline in index.html.
            page.goto(url, wait_until="domcontentloaded")

            # Single evaluate() call: set inputs, processInput(), singleFMC(0),
            # return innerHTML of #singleoutput.
            raw_output = bridge.inject_run_and_capture(page, panel_text, target_text)

        finally:
            browser.close()

    return raw_output
