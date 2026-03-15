"""report/theme.py — Color palettes and chart color sets."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Chart colors — consistent across themes
# ---------------------------------------------------------------------------

COUNTRY_COLORS = [
    "#4a8ef5", "#6aa8ff", "#3476e0", "#2060c8",
    "#7ab8ff", "#5094e8", "#8ec8ff",
]

MACRO_COLORS = [
    "#c8924a", "#e8b870",
    "#a07030", "#d4a050",
]

SAMPLE_COLORS = [
    "#22c593", "#3dd8a8", "#18a878",
    "#0e8a60", "#50e8bc", "#14b884",
]

PERIOD_COLORS = [
    "#9b72f5", "#b898ff", "#7c58e0",
    "#6040c8", "#c0a0ff", "#8868e8",
]

# ---------------------------------------------------------------------------
# CSS variable palettes
# ---------------------------------------------------------------------------

DARK_VARS = """\

  /* Palette — "Gilded Archive" */
  --bg:        #06060c;
  --bg-1:      #0c0c18;
  --bg-2:      #11111e;
  --bg-3:      #171728;
  --bg-4:      #1d1d32;
  --border:    #1c1c30;
  --border-2:  #24243a;
  --border-3:  #2e2e48;

  --gold:      #c8924a;
  --gold-2:    #e8b870;
  --gold-3:    #f5d090;
  --gold-dim:  rgba(200,146,74,0.08);
  --gold-dim2: rgba(200,146,74,0.15);

  --ink:       #ede8e0;
  --ink-2:     #8a8898;
  --ink-3:     #4e4c60;
  --ink-4:     #2c2a3c;

  --blue:      #4a8ef5;
  --blue-dim:  rgba(74,142,245,0.10);
  --green:     #22c593;
  --green-dim: rgba(34,197,147,0.10);
  --red:       #e05555;
  --red-dim:   rgba(224,85,85,0.10);
  --amber:     #e6a01e;
  --amber-dim: rgba(230,160,30,0.10);

  /* Typography stacks */
  --font-serif:   "Palatino Linotype", "Palatino", "Book Antiqua", Georgia, serif;
  --font-display: "Optima", "Candara", "Gill Sans MT", "Gill Sans", Calibri, sans-serif;
  --font-ui:      -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  --font-mono:    "Cascadia Code", "SF Mono", "Consolas", "Courier New", monospace;

  /* Shadows */
  --shadow-xs: 0 1px 3px rgba(0,0,0,0.65);
  --shadow-sm: 0 2px 8px rgba(0,0,0,0.55);
  --shadow:    0 4px 20px rgba(0,0,0,0.55);
  --shadow-lg: 0 8px 40px rgba(0,0,0,0.65);
  --shadow-xl: 0 16px 64px rgba(0,0,0,0.75);"""


LIGHT_VARS = """\

  /* Palette — light "Parchment" */
  --bg:        #f4f0e8;
  --bg-1:      #ffffff;
  --bg-2:      #f8f4ec;
  --bg-3:      #ede8dc;
  --bg-4:      #e6e0d0;
  --border:    #d8d0c0;
  --border-2:  #ccc4b0;
  --border-3:  #b8b0a0;

  --gold:      #9a6a18;
  --gold-2:    #b07a20;
  --gold-3:    #c89030;
  --gold-dim:  rgba(154,106,24,0.10);
  --gold-dim2: rgba(154,106,24,0.18);

  --ink:       #1c1814;
  --ink-2:     #5a5448;
  --ink-3:     #9a9080;
  --ink-4:     #c4bca8;

  --blue:      #1a5ec0;
  --blue-dim:  rgba(26,94,192,0.08);
  --green:     #0d7050;
  --green-dim: rgba(13,112,80,0.08);
  --red:       #c02828;
  --red-dim:   rgba(192,40,40,0.08);
  --amber:     #b86810;
  --amber-dim: rgba(184,104,16,0.08);

  --font-serif:   "Palatino Linotype", "Palatino", "Book Antiqua", Georgia, serif;
  --font-display: "Optima", "Candara", "Gill Sans MT", "Gill Sans", Calibri, sans-serif;
  --font-ui:      -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  --font-mono:    "Cascadia Code", "SF Mono", "Consolas", "Courier New", monospace;

  --shadow-xs: 0 1px 2px rgba(0,0,0,0.08);
  --shadow-sm: 0 2px 6px rgba(0,0,0,0.08);
  --shadow:    0 4px 16px rgba(0,0,0,0.10);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.12);
  --shadow-xl: 0 16px 64px rgba(0,0,0,0.16);"""
