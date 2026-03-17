"""
engine/result_parser.py — parse raw Vahaduo singleFMC HTML output into structured data.

Output format confirmed from github.com/vahaduo/vahaduo singleFMC() (commit dac51dff):

    <table>
      <tr>
        <th colspan='2' class='singleheader'>
          Target: PopulationName<br/>
          Distance: 1.2345% / 0.01234567<br/>
          <div class="singleinfo nonselectable" data-nonselectable="..."></div>
        </th>
      </tr>
      <tr>
        <td class="singleleftcolumn">42.1</td>
        <td class="singlerightcolumn">Population_A</td>
      </tr>
      <tr>
        <td class="singleleftcolumn">18.7</td>
        <td class="singlerightcolumn">Population_B</td>
      </tr>
      ...
    </table>

Notes:
  - Distance is stored as a raw float (e.g. 0.01234567) and also shown as percent
  - Population percentages are stored as floats 0-100 (e.g. 42.1 means 42.1%)
  - Only non-zero populations are printed by default (printZeroes is false)
  - Multiple results are separated by <br><hr> (printOutput prepends newest first)
"""

from __future__ import annotations

import re

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class PopulationResult(BaseModel):
    """A single source population entry in a Vahaduo distance result."""
    name: str
    percent: float


class RunResult(BaseModel):
    """Structured output from one Vahaduo singleFMC run."""
    distance: float
    populations: list[PopulationResult]
    raw_output: str


# ---------------------------------------------------------------------------
# Regex patterns (derived from confirmed singleFMC output format)
# ---------------------------------------------------------------------------

# Matches: "Distance: 1.2345% / 0.01234567"
# Group 1 = raw distance float
_DISTANCE_RE = re.compile(
    r"Distance:\s*[\d.]+%\s*/\s*([\d.]+)",
    re.IGNORECASE,
)

# Matches: singleleftcolumn">42.1</td><td class="singlerightcolumn">Population_A</td>
# Group 1 = percent string, Group 2 = population name
_POP_ROW_RE = re.compile(
    r'singleleftcolumn">([\d.]+)</td>'
    r'<td class="singlerightcolumn">([^<]+)</td>',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_result(raw: str) -> RunResult:
    """
    Parse the innerHTML of div#singleoutput into a structured RunResult.

    Parameters
    ----------
    raw:
        The raw HTML string returned by VahaduoBridge.inject_run_and_capture().
        Contains one or more result tables; only the first (most recent) is parsed.

    Returns
    -------
    RunResult

    Raises
    ------
    ValueError
        If the distance line or population rows cannot be found in the output.
    """
    if not raw or not raw.strip():
        raise ValueError(
            "Empty result from Vahaduo engine. "
            "Check that source panel and target were set correctly."
        )

    # When multiple runs accumulate in #singleoutput, they are separated by
    # <br><hr>. Take only the first block (most recent result).
    first_block = raw.split("<br><hr>")[0]

    # --- Extract distance ---
    dist_match = _DISTANCE_RE.search(first_block)
    if not dist_match:
        raise ValueError(
            "Could not find distance value in Vahaduo output. "
            f"Raw output (first 500 chars): {raw[:500]}"
        )
    distance = float(dist_match.group(1))

    # --- Extract populations ---
    populations = [
        PopulationResult(
            percent=float(m.group(1)),
            name=m.group(2).strip(),
        )
        for m in _POP_ROW_RE.finditer(first_block)
    ]

    if not populations:
        raise ValueError(
            "No population rows found in Vahaduo output. "
            "Check that the source panel contains valid G25 data. "
            f"Raw output (first 500 chars): {raw[:500]}"
        )

    return RunResult(
        distance=distance,
        populations=populations,
        raw_output=raw,
    )
