"""
engine/vahaduo_bridge.py — JS interaction bridge for the Vahaduo inline engine.

Implementation is based on the inspection of github.com/vahaduo/vahaduo (commit dac51dff).

Execution model (confirmed by engine/inspector.py):
  - All logic is inline JS in index.html (52K chars, no external JS files)
  - Source data goes into textarea#source
  - Target data goes into textarea#target
  - Both textareas have onchange="inputHasChanged = true"
  - processInput() parses both into sourceArray/targetArray when inputHasChanged=true
  - singleFMC(targetId) runs FastMonteCarlo for one target and writes HTML to #singleoutput
  - printOutput(html, 'singleoutput') prepends the HTML result into div#singleoutput

Bridge strategy (Path A — direct JS function call):
  1. Set textarea values via page.evaluate()
  2. Set inputHasChanged = true and call processInput() via page.evaluate()
  3. Call singleFMC(0) via page.evaluate()
  4. Return div#singleoutput.innerHTML via page.evaluate()

All selectors and function names are taken verbatim from .inspection.json.
"""

from __future__ import annotations

# ── Confirmed selectors and function names (from .inspection.json) ──────────
SOURCE_SELECTOR = "#source"
TARGET_SELECTOR = "#target"
RESULT_SELECTOR = "#singleoutput"

# The JS evaluated in one shot: set inputs, process, run, return raw HTML.
# Returns the innerHTML of #singleoutput immediately after singleFMC(0) completes.
_INJECT_RUN_AND_CAPTURE_JS = """
([panelText, targetText]) => {
    // Clear any previous output so we get only the latest result
    document.getElementById('singleoutput').innerHTML = '';

    // Set source panel and target in their respective textareas
    document.getElementById('source').value = panelText;
    document.getElementById('target').value = targetText;

    // The onchange handler only fires on user interaction, not JS assignment.
    // Set the flag directly and call processInput() to parse both inputs.
    inputHasChanged = true;
    processInput();

    // Run the single-population fitting model for target index 0.
    // singleFMC() is a synchronous call — it writes to #singleoutput before returning.
    singleFMC(0);

    // Return the raw HTML written by printOutput() into the result container.
    return document.getElementById('singleoutput').innerHTML;
}
"""


class VahaduoBridge:
    """
    Encapsulates all page.evaluate() calls against the Vahaduo inline engine.

    All JS interaction is isolated here. No other module should touch the
    Playwright Page object directly.
    """

    def inject_and_run(
        self,
        page: object,
        panel_text: str,
        target_text: str,
    ) -> None:
        """
        Inject source panel and target text, trigger processInput(), and run singleFMC(0).

        Results are written to div#singleoutput inside the page. Call
        extract_result() afterwards to retrieve them.

        NOTE: This implementation calls inject_run_and_capture() internally.
        Both methods are provided for API symmetry with the runner contract;
        in practice, use inject_run_and_capture() directly for efficiency.

        Parameters
        ----------
        page:
            A Playwright Page (sync API) with the local Vahaduo page loaded.
        panel_text:
            G25 source panel string (output of panel_builder.build_panel()).
        target_text:
            G25 target string — single population in panel format.
        """
        # Store for extract_result() to return
        self._last_raw: str = page.evaluate(  # type: ignore[attr-defined]
            _INJECT_RUN_AND_CAPTURE_JS,
            [panel_text, target_text],
        )

    def extract_result(self, page: object) -> str:
        """
        Return the raw HTML result string captured during inject_and_run().

        Parameters
        ----------
        page:
            A Playwright Page (sync API). Not used here — result was captured
            synchronously during inject_and_run().

        Returns
        -------
        str
            Raw innerHTML of div#singleoutput after singleFMC(0) completed.
        """
        return self._last_raw

    def inject_run_and_capture(
        self,
        page: object,
        panel_text: str,
        target_text: str,
    ) -> str:
        """
        Convenience method: inject inputs, run singleFMC(0), and return raw HTML
        in a single page.evaluate() call.

        Parameters
        ----------
        page:
            A Playwright Page (sync API) with the local Vahaduo page loaded.
        panel_text:
            G25 source panel string.
        target_text:
            G25 target string (single population, panel format).

        Returns
        -------
        str
            Raw innerHTML of div#singleoutput.
        """
        raw: str = page.evaluate(  # type: ignore[attr-defined]
            _INJECT_RUN_AND_CAPTURE_JS,
            [panel_text, target_text],
        )
        return raw
