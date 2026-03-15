# Report Generator — Development Rules

This file governs all work inside `report/`. It is the authoritative spec for the HTML report system.

---

## Package structure

```
report/
  __init__.py       — re-exports make_report, cmd_make_report, render_report
  make_report.py    — orchestration + CLI (g25-make-report)
  templates.py      — HTML fragment builders and render_report()
  assets.py         — get_css() and get_js() (all CSS/JS inline)
  theme.py          — color palettes (COUNTRY_COLORS, MACRO_COLORS, etc.) + CSS variable blocks
  CLAUDE.md         — this file
```

---

## CLI

```
g25-make-report data/users/<user_id>
g25-make-report data/users/<user_id> --theme light
```

Output: `data/users/<user_id>/report/report.html` (self-contained, no external deps)

---

## Input data sources (priority order)

| Data | Primary | Fallback 1 | Fallback 2 |
|---|---|---|---|
| period_data | `analysis/latest/period_comparison.json` | `evidence_pack.json → period_comparison` | `final_report.json → periods.comparison` |
| generic_summary | `analysis/latest/generic_summary.json` | — | — |
| interpretation | `interpretation/interpretation.txt` | graceful placeholder | — |

Required files (must exist or raise FileNotFoundError):
- `input/profile.json`
- `analysis/latest/final_report.json`
- `analysis/latest/aggregated_result.json`

---

## Section order (FIXED — do not reorder)

| Letter | ID | Section title | Collapsible |
|---|---|---|---|
| A | `overview` | Hero / Executive Summary | No |
| B | `ancestry` | Ancestry Distribution | Yes, default open |
| C | `interpretation` | Historical Interpretation + Period Signal card | Yes, default open |
| D | `samples` | Sample-Level Proxies | Yes, default open |
| E | `technical` | Technical Appendix | Yes, default **collapsed** |

TOC sidebar has 5 links (A–E).

---

All sections B–E have a `collapsible-section` class and a `.collapsible-toggle` button in their header.
Technical Appendix additionally has the `collapsed` class (starts hidden).

---

## Period signal — placement rules

Period data is displayed in **two places**, never as a standalone section:

1. **Compact card** (`_period_signal_card`) — appended after interpretation prose in section C
   - Shows: best period name, approximate date range, one fixed sentence
   - Fixed sentence: "This is the closest single-period approximation. The overall mixed-period model remains the primary result."
   - Hidden entirely if no period data

2. **Detail subsection** (`_period_detail_block`) — inside the Technical Appendix (section E)
   - Uses native `<details>/<summary>` element with summary text "Period Diagnostics"
   - Contains: best-period callout, inverted bar chart, reference table
   - If no data: shows "Period diagnostics were not generated for this run."
   - Always present in the appendix (even when empty)

---

## Data hierarchy (FIXED — do not reorder)

1. `by_country` — **primary evidence display** (donut + bars, largest visual)
2. `by_macro_region` — **secondary** (smaller donut, supplemental)
3. `top_samples` — **supporting detail** (section D)
4. Period diagnostics — **diagnostic context only**, compact card in C + detail in E appendix

---

## Chart rules

### by_country donut (primary, section B)
- SVG stroke-dasharray technique — per-segment rotation
- `transform="rotate(start_angle cx cy)"` per segment (no group rotate)
- `stroke-dasharray="{arc} {circumference - arc}"` — period = circumference
- Start angle formula: `cumulative_pct / 100 * 360 - 90`
- `overflow="visible"` on `<svg>` — prevents stroke clipping
- `width="100%"` + `max-width:{size}px` — responsive
- Center label: two-line — "Ancestry" / "Distribution"
- Size: 200px for primary, 160px for macro
- Colors: `_geo_color(label, colors, idx)` — Europe=blue, Levant=amber (see below)

### Ancestry layout (section B)
- `.ancestry-layout` grid: donut on LEFT, ranked bars on RIGHT
- CSS: `grid-template-columns: auto 1fr`
- Collapses to single column below 680px

### Period detail chart (appendix, section E)
- Inverted bar chart: lower distance = longer bar
- Period labels are title-cased via `_fmt_period()`
- Show `.period-best-callout` if `best_period` is available
- Show `<table class="period-table">` with Period / Approx. Years / Distance columns
- Use `_PERIOD_RANGES` dict for date ranges
- "No data" message: `"Period diagnostics were not generated for this run."`

### Sample cards (section D)
- `_parse_sample_name(name)` extracts `(country, period)` from G25 sample IDs
- Show country (colored) and period label below the sample name
- Proxy disclaimer note above card list
- Colors: `_geo_color(country, SAMPLE_COLORS, idx)`

---

## Geographic color mapping

Single source of truth: `_geo_color(label, fallback, idx)` in `templates.py`

| Region | Color family |
|---|---|
| Europe, Italy, Croatia, Greece, Spain, etc. | `_EUROPE_BLUES` |
| Israel, Turkey, Levant, MENA, MLBA, etc. | `_LEVANT_AMBERS` |
| All others | fallback colors array |

Applied in: `_svg_donut()`, `_bar_rows()`, `_sample_cards()`

---

## Theme system

- Default theme: `dark`
- Both palettes always embedded: `html[data-theme='dark']` and `html[data-theme='light']`
- Specificity: `html[data-theme='X']` (0,1,1) beats `:root` (0,1,0) — critical
- Toggle wired via `.theme-toggle-btn` class (not ID) — appears in both sidebar and mobile nav
- Persisted to `localStorage` key `g25-theme`

---

## Content rules

- `interpretation.txt` is the ONLY source for narrative prose — never invent text
- Placeholder if missing: "Historical interpretation has not yet been added."
- Executive summary: auto-derived from `final_report.json` data only
- All ancient populations described as "genetic proxies" — never "ancestors"
- Technical Appendix: collapsed by default (`collapsed` class on section)

---

## Design aesthetic — "The Gilded Archive"

- Dark navy background (`--bg: #06060c`) with warm amber gold (`--gold: #c8924a`) accents
- Fonts: `--font-serif` (Palatino) for prose; `--font-display` (Optima/Candara) for UI labels; `--font-mono` for data
- Animated grain texture overlay (SVG noise, `body::before`)
- Section cards: rounded corners (20px), subtle border, `var(--bg-2)` background
- Staggered entry animations (`.section:nth-child` delays)
- Bar shimmer sweep after animate-in
- Donut segment hover: brightness + glow drop-shadow

---

## Output rules

- Output file: `report/report.html`
- Self-contained: all CSS and JS inline, no CDN, no external resources
- Deterministic: same inputs → identical HTML output every time
- Do NOT add CDN references, external scripts, or external stylesheets

---

## Skill requirement

**Always invoke the `frontend-design` skill before making visual changes to `assets.py` or `templates.py`.**

---

## Testing

Test file: `tests/test_make_report.py`

Required coverage:
- File creation at `report/report.html`
- All 5 section headings present in HTML (A–E)
- "Historical Period Signal" card present when period data available; hidden when not
- "not generated" message in appendix when no period data
- "Period Diagnostics" always present (appendix `<summary>` tag)
- Key data fields present (display_name, distance, profile, country names, etc.)
- Missing optional files handled gracefully (interpretation, period data, generic_summary)
- Required files missing → FileNotFoundError
- render_report() deterministic
- No CDN references in output
- CLI smoke test
