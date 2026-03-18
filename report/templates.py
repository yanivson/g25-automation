"""report/templates.py — HTML fragment builders and full report renderer."""

from __future__ import annotations

import math
import re

from .assets import get_css, get_js
from .theme import (
    COUNTRY_COLORS, MACRO_COLORS, SAMPLE_COLORS, PERIOD_COLORS,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _esc(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Geographic color mapping
# Europe  → blue family;  Levant / MENA → amber/gold family
# ---------------------------------------------------------------------------

_EUROPE_BLUES = [
    "#3d7ef5", "#5b9cf5", "#4a8ee8", "#6ab0f5",
    "#2d6de0", "#7ac0ff", "#5090e8", "#4d85e0",
]
_LEVANT_AMBERS = [
    "#d4a03a", "#e0b840", "#c89030", "#dab040",
    "#c8921a", "#e8ba50", "#d09030", "#e0a828",
]

_GEO_MAP: list[tuple[list[str], list[str]]] = [
    # ── European ────────────────────────────────────────────────
    (["italy", "italian", "southern europe", "southern european",
      "croatia", "greek", "greece", "spain", "portugal",
      "france", "german", "austria", "czech", "slovak",
      "polish", "poland", "serbian", "serbia", "albanian",
      "bulgarian", "romania", "romanian", "hungarian", "hungary",
      "balkan", "slavic", "nordic", "scandina", "viking",
      "europe", "european", "western", "eastern europe"],
     _EUROPE_BLUES),
    # ── Levant / MENA ───────────────────────────────────────────
    (["israel", "israeli", "levant", "levantine",
      "lebanon", "lebanese", "syria", "syrian",
      "jordan", "jordanian", "palestine", "palestinian",
      "iraq", "iraqi", "iran", "iranian", "persian",
      "turkey", "turkish", "anatolia", "anatolian",
      "arab", "arabic", "saudi", "yemen", "gulf",
      "egypt", "egyptian", "north africa", "maghreb",
      "tunisia", "morocco", "algeria", "libya",
      "eastern mediterranean", "east med", "bronze age levant",
      "mlba", "iron age levant", "chalcolithic"],
     _LEVANT_AMBERS),
]


def _geo_color(label: str, fallback: list[str], idx: int) -> str:
    """Return a geographically-appropriate color for a country/region label."""
    low = label.lower()
    for keywords, palette in _GEO_MAP:
        if any(k in low for k in keywords):
            return palette[idx % len(palette)]
    return fallback[idx % len(fallback)]


# ---------------------------------------------------------------------------
# Display-layer region label remapping
# ---------------------------------------------------------------------------

# Maps internal region keys (used for calculations) to historically appropriate
# display labels. Applied only at render time — data keys are never modified.
_DISPLAY_REGION_MAP: dict[str, str] = {
    # All "Turkey_*" entries in G25 ancient panels are ancient Anatolian samples.
    # "Anatolia" is the geographically and historically accurate display label.
    "Turkey": "Anatolia",
}


def _display_region(region: str, sample_name: str = "") -> str:
    """Return the display label for a region. Leaves unlisted regions unchanged."""
    return _DISPLAY_REGION_MAP.get(region, region)


# ---------------------------------------------------------------------------
# Country list grouping helpers
# ---------------------------------------------------------------------------

def _geo_family(label: str) -> str:
    """Classify a region label into a broad family for 'Other X' bucket labeling."""
    low = label.lower()
    _EUR = ["italy", "croatia", "greece", "spain", "portugal", "france", "german",
            "austria", "czech", "slovak", "polish", "poland", "serbian", "serbia",
            "albanian", "bulgarian", "romania", "hungarian", "balkan", "slavic",
            "nordic", "scandina", "europe", "european", "latvia", "lithuania",
            "estonia", "finland", "anatolia", "turkey", "turkish"]
    _MED = ["israel", "levant", "lebanon", "syria", "jordan", "palestine",
            "iraq", "iran", "arab", "egypt", "north africa", "maghreb",
            "tunisia", "morocco", "algeria", "libya"]
    if any(k in low for k in _EUR):
        return "European"
    if any(k in low for k in _MED):
        return "Mediterranean"
    return "Near Eastern"


def _euro_subregion(label: str) -> str:
    """Map a European region label to a sub-region name for display hints."""
    low = label.lower()
    if any(k in low for k in ["latvia", "lithuania", "estonia", "baltic"]):
        return "Baltic"
    if any(k in low for k in ["croatia", "serbian", "serbia", "albanian", "bulgarian",
                               "romania", "romanian", "balkan", "greek", "greece",
                               "bosnian", "macedon", "monten"]):
        return "Balkan"
    if any(k in low for k in ["polish", "poland", "czech", "slovak", "hungarian",
                               "hungary", "central europe"]):
        return "Central Europe"
    if any(k in low for k in ["ukrainian", "belarus", "russian", "moldov",
                               "eastern europe"]):
        return "Eastern Europe"
    return "Western Europe"


def _group_small_countries(
    entries: list[dict],
    region_key: str = "region",
    percent_key: str = "percent",
    threshold: float = 2.0,
) -> list[dict]:
    """Group entries below *threshold*% (excluding the top contributor) into
    geo-labeled 'Other X' buckets.

    European buckets include sub-region hints: 'Other European (Baltic/Balkan)'.
    At most 2 sub-region names are shown to avoid clutter.
    """
    if not entries:
        return entries
    top = entries[0]
    rest = entries[1:]
    main = [e for e in rest if float(e.get(percent_key, 0)) >= threshold]
    small = [e for e in rest if float(e.get(percent_key, 0)) < threshold]
    if not small:
        return entries
    buckets: dict[str, float] = {}
    euro_subs: list[str] = []  # ordered, deduped sub-regions for European bucket
    for e in small:
        fam = _geo_family(str(e.get(region_key, "")))
        buckets[fam] = buckets.get(fam, 0.0) + float(e.get(percent_key, 0))
        if fam == "European":
            sub = _euro_subregion(str(e.get(region_key, "")))
            if sub not in euro_subs:
                euro_subs.append(sub)
    other_entries: list[dict] = []
    for fam, pct in sorted(buckets.items(), key=lambda x: -x[1]):
        if fam == "European" and euro_subs:
            hint = "/".join(euro_subs[:2])
            lbl = f"Other European ({hint})"
        else:
            lbl = f"Other {fam}"
        other_entries.append({region_key: lbl, percent_key: round(pct, 2)})
    return [top] + main + other_entries


# ---------------------------------------------------------------------------
# Sample name parser — extract country + period from G25 sample IDs
# ---------------------------------------------------------------------------

_PERIOD_KEYWORDS: list[tuple[list[str], str]] = [
    (["mlba", "_ba_", "bronze", "elba", "mba", "lba", "eba"], "Bronze Age"),
    (["iron", "_ia_", "ironage", "phoeni"],                    "Iron Age"),
    (["classical", "hellenistic", "archaic"],                  "Classical"),
    (["imperial", "empire"],                                   "Roman Imperial"),
    (["roman", "rome", "_rom"],                                "Roman"),
    (["byzantine", "byzan", "earlybyzan"],                     "Byzantine"),
    (["medieval", "medieva"],                                  "Medieval"),
    (["lateant", "late_ant", "lateanq"],                       "Late Antiquity"),
    (["modern", "present", "contemporary"],                    "Modern"),
    (["neolithic", "neo", "ln", "bkg", "cordedware"],          "Neolithic"),
    (["chalcolithic", "copper", "eneolithic"],                 "Chalcolithic"),
]


def _parse_sample_name(name: str) -> tuple[str, str]:
    """Return (country, period_label) extracted from a G25 sample ID."""
    parts = name.split("_")
    country = parts[0] if parts else name

    # Token-based matching to prevent false positives (e.g. "eba" inside "lebanon").
    # Strip file-extension suffixes (.SG, .DG) so "Roman.SG" → "roman".
    # Hybrid rule: keywords with len ≥ 5 use substring matching (so "byzan" matches
    # inside "earlybyzantine"); shorter keywords use exact token equality only
    # (so "eba" doesn't match "lebanon").
    tokens = {t.lower().split(".")[0] for t in parts}
    period = ""
    for keywords, label in _PERIOD_KEYWORDS:
        for k in keywords:
            kk = k.strip("_")
            if len(kk) >= 5:
                matched = any(kk in t for t in tokens)
            else:
                matched = kk in tokens
            if matched:
                period = label
                break
        if period:
            break

    return country, period


# ---------------------------------------------------------------------------
# Period date ranges reference
# ---------------------------------------------------------------------------

_PERIOD_RANGES: dict[str, str] = {
    "bronze age":       "~3000 – 1200 BCE",
    "iron age":         "~1200 – 500 BCE",
    "classical":        "~500 BCE – 200 CE",
    "late antiquity":   "~200 – 700 CE",
    "medieval":         "~700 – 1500 CE",
    "roman":            "~500 BCE – 400 CE",
    "roman imperial":   "~27 BCE – 476 CE",
    "byzantine":        "~330 – 1453 CE",
    "neolithic":        "~7000 – 3000 BCE",
    "chalcolithic":     "~4500 – 3000 BCE",
}


# ---------------------------------------------------------------------------
# SVG Donut chart  (stroke-dasharray technique)
# ---------------------------------------------------------------------------

def _svg_donut(
    items: list[dict],
    label_key: str,
    pct_key: str,
    colors: list[str],
    size: int = 180,
    chart_id: str = "d0",
    center_label: str = "",
) -> str:
    if not items:
        return '<p class="no-data">No data available.</p>'

    cx = cy = size / 2
    r = size * 0.32
    stroke_w = size * 0.13
    gap_deg = 1.8

    circumference = 2 * math.pi * r
    total = sum(float(item[pct_key]) for item in items)
    if total == 0:
        return '<p class="no-data">No data.</p>'

    segs: list[str] = []
    leg_items: list[str] = []
    cumulative_pct = 0.0

    for i, item in enumerate(items):
        label = str(item[label_key])
        orig_pct = float(item[pct_key])
        norm_pct = orig_pct / total * 100
        color = _geo_color(label, colors, i)

        arc_deg = norm_pct / 100 * 360 - gap_deg
        arc_deg = max(arc_deg, 0.5)
        arc = arc_deg / 360 * circumference
        gap = circumference - arc

        start_angle = cumulative_pct / 100 * 360 - 90

        segs.append(
            f'<circle class="donut-seg" data-idx="{i}"'
            f' cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}"'
            f' fill="none" stroke="{color}" stroke-width="{stroke_w:.2f}"'
            f' stroke-dasharray="{arc:.3f} {gap:.3f}"'
            f' transform="rotate({start_angle:.3f} {cx:.2f} {cy:.2f})"'
            f' data-label="{_esc(label)}" data-pct="{orig_pct:.1f}">'
            f'<title>{_esc(label)}: {orig_pct:.1f}%</title>'
            f'</circle>'
        )
        leg_items.append(
            f'<div class="leg-item" data-idx="{i}">'
            f'<span class="leg-dot" style="background:{color}"></span>'
            f'<span class="leg-text">{_esc(label)}</span>'
            f'<span class="leg-pct">{orig_pct:.1f}%</span>'
            f'</div>'
        )
        cumulative_pct += norm_pct

    # Two-line center label — supports "Line1\nLine2" syntax
    if "\n" in center_label:
        line1, line2 = center_label.split("\n", 1)
    else:
        line1 = center_label or "Ancestry"
        line2 = "Distribution"

    center_svg = (
        f'<text x="{cx:.2f}" y="{cy - 6:.2f}" text-anchor="middle"'
        f' class="donut-center-val">{_esc(line1)}</text>'
        f'<text x="{cx:.2f}" y="{cy + 12:.2f}" text-anchor="middle"'
        f' class="donut-center-lbl">{_esc(line2)}</text>'
    )

    svg = (
        f'<svg class="donut-chart" id="{chart_id}"'
        f' viewBox="0 0 {size} {size}"'
        f' width="100%" style="max-width:{size}px"'
        f' overflow="visible"'
        f' role="img" aria-label="Ancestry donut chart">'
        + "".join(segs)
        + center_svg
        + "</svg>"
    )
    legend = "<div class=\"donut-legend\">" + "".join(leg_items) + "</div>"

    return (
        f'<div class="donut-outer" id="{chart_id}-wrap">'
        f'<div class="donut-ring-wrap">{svg}</div>'
        f"{legend}</div>"
    )


# ---------------------------------------------------------------------------
# Horizontal bar chart
# ---------------------------------------------------------------------------

def _bar_rows(
    items: list[dict],
    label_key: str,
    pct_key: str,
    colors: list[str],
) -> str:
    if not items:
        return '<p class="no-data">No data available.</p>'
    max_pct = max(float(item[pct_key]) for item in items) or 1
    rows: list[str] = []
    for i, item in enumerate(items):
        raw_label = str(item[label_key])
        # Bold the top contributor; dim entries < 5% (but never the top)
        label_html = f'<strong>{_esc(raw_label)}</strong>' if i == 0 else _esc(raw_label)
        pct = float(item[pct_key])
        bar_w = pct / max_pct * 100
        color = _geo_color(raw_label, colors, i)
        dim = ' style="opacity:0.68"' if (pct < 5.0 and i > 0) else ""
        rows.append(
            f'<div class="bar-row"{dim}>'
            f'<span class="bar-label">{label_html}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill" data-w="{bar_w:.1f}%" style="background:{color}"></div>'
            f'</div>'
            f'<span class="bar-pct">{pct:.1f}%</span>'
            f'</div>'
        )
    return '<div class="bar-list">' + "".join(rows) + "</div>"


# ---------------------------------------------------------------------------
# Sample cards — with geographic region + period extracted from name
# ---------------------------------------------------------------------------

def _sample_cards(samples: list[dict]) -> str:
    if not samples:
        return '<p class="no-data">No sample data available.</p>'

    # Separate main samples (≥1%) from minor contributors (<1%).
    # Minor samples are omitted from cards for visual consistency with the
    # main ancestry chart which also groups <1% entries.
    main_samples = [s for s in samples if float(s["percent"]) >= 1.0]
    minor_samples = [s for s in samples if float(s["percent"]) < 1.0]
    display_samples = main_samples if main_samples else samples

    total = sum(float(s["percent"]) for s in samples) or 1
    cards: list[str] = []
    for i, s in enumerate(display_samples):
        raw_name = s["name"]
        pct = float(s["percent"])
        bar_w = pct / total * 100
        country, period = _parse_sample_name(raw_name)
        country_label = _display_region(country, raw_name)
        color = _geo_color(country_label, SAMPLE_COLORS, i)

        meta_parts: list[str] = []
        if country_label:
            meta_parts.append(
                f'<span class="sample-country" style="color:{color}">'
                f'{_esc(country_label)}</span>'
            )
        if period:
            meta_parts.append(f'<span class="sample-period">{_esc(period)}</span>')
        meta_html = (
            f'<div class="sample-meta">{"&ensp;·&ensp;".join(meta_parts)}</div>'
            if meta_parts else ""
        )

        cards.append(
            f'<div class="sample-card">'
            f'<div class="sample-rank" style="background:{color}">{i + 1}</div>'
            f'<div class="sample-body">'
            f'<div class="sample-name">{_esc(raw_name)}</div>'
            f'{meta_html}'
            f'<div class="sample-mini-track">'
            f'<div class="sample-mini-fill" data-w="{bar_w:.1f}%"'
            f' style="background:{color};width:0"></div>'
            f'</div></div>'
            f'<div class="sample-pct">{pct:.1f}%</div>'
            f'</div>'
        )
    note = (
        '<p class="sample-note">'
        'Ancient samples serve as genetic <em>proxies</em> — '
        'they are reference populations, not direct ancestors.'
        '</p>'
    )
    minor_note = ""
    if minor_samples:
        minor_pct = sum(float(s["percent"]) for s in minor_samples)
        n = len(minor_samples)
        minor_note = (
            f'<p class="sample-note" style="margin-top:0.4rem">'
            f'{n} additional sample{"s" if n > 1 else ""} contribute '
            f'{minor_pct:.1f}% combined (each &lt;1%).'
            f'</p>'
        )
    return note + '<div class="sample-list">' + "".join(cards) + "</div>" + minor_note


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

def _fmt_period(name: str) -> str:
    """Format a period name for display: 'late_antiquity' → 'Late Antiquity'."""
    return name.replace("_", " ").title()


def _extract_periods(
    period_data: dict | list | None,
    best_period: str | None = None,
) -> tuple[list[dict], str | None]:
    """Normalize any period_data format → (periods list, best_period)."""
    periods: list[dict] = []
    if isinstance(period_data, list):
        periods = period_data
    elif isinstance(period_data, dict):
        if "period_results" in period_data:
            periods = [
                {"period": r["period"], "distance": r["best_distance"]}
                for r in period_data["period_results"]
                if not r.get("skipped") and r.get("best_distance") is not None
            ]
            if best_period is None:
                ranked = period_data.get("ranked_by_distance") or []
                if ranked:
                    best_period = ranked[0]["period"]
        else:
            periods = (
                period_data.get("periods")
                or period_data.get("comparison")
                or []
            )
            if best_period is None:
                best_period = period_data.get("best_period")

    if not best_period and periods:
        best_entry = min(
            periods,
            key=lambda p: float(p.get("distance", p.get("best_distance", 0))),
        )
        best_period = str(best_entry.get("period") or best_entry.get("name", ""))

    return periods, best_period or None


def _period_signal_card(
    period_data: dict | list | None,
    best_period: str | None = None,
) -> str:
    """Compact 'Historical Period Signal' card. Returns '' when no data."""
    periods, best_period = _extract_periods(period_data, best_period)
    if not best_period:
        return ""

    best_label = _fmt_period(str(best_period))
    date_range = _PERIOD_RANGES.get(best_label.lower(), "")
    years_html = (
        f'<span class="period-signal-years">{_esc(date_range)}</span>'
        if date_range else ""
    )
    return (
        f'<div class="period-signal-card">'
        f'<div class="period-signal-header">'
        f'<span class="period-signal-icon">&#9719;</span>'
        f'<span class="period-signal-title">Historical Period Signal</span>'
        f'</div>'
        f'<div class="period-signal-main">'
        f'<span class="period-signal-value">{_esc(best_label)}</span>'
        f'{years_html}'
        f'</div>'
        f'<p class="period-signal-note">'
        f'This is the closest single-period approximation. '
        f'The overall mixed-period model remains the primary result.'
        f'</p>'
        f'</div>'
    )


def _period_detail_block(
    period_data: dict | list | None,
    best_period: str | None = None,
) -> str:
    """Full period bar chart + table for the Technical Appendix."""
    periods, best_period = _extract_periods(period_data, best_period)

    if not periods:
        return '<div class="no-data">Period diagnostics were not generated for this run.</div>'

    html_parts: list[str] = []

    # Best period callout
    if best_period:
        html_parts.append(
            f'<div class="period-best-callout">'
            f'<span class="period-best-label">Best Period Fit</span>'
            f'<span class="period-best-value">{_esc(_fmt_period(str(best_period)))}</span>'
            f'</div>'
        )

    dists = [float(p.get("distance", 0)) for p in periods]
    max_d = max(dists) if dists else 1
    min_d = min(dists) if dists else 0
    best_idx = dists.index(min_d) if dists else 0

    # Bar chart (inverted — lower distance = longer bar)
    rows: list[str] = []
    for i, (p, dist) in enumerate(zip(periods, dists)):
        label = _fmt_period(str(p.get("period") or p.get("name", f"Period {i + 1}")))
        spread = max_d - min_d if max_d > min_d else max_d
        inv_w = ((max_d - dist) / spread * 100) if spread > 0 else 50
        color = PERIOD_COLORS[i % len(PERIOD_COLORS)]
        best_mark = " ★" if i == best_idx else ""
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{_esc(label)}{_esc(best_mark)}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill" data-w="{inv_w:.1f}%" style="background:{color}"></div>'
            f'</div>'
            f'<span class="bar-pct" style="font-size:0.75rem;color:var(--ink-3)">'
            f'{dist:.5f}</span>'
            f'</div>'
        )
    note = (
        '<p class="period-note">Longer bar = closer genetic fit (lower distance).'
        ' ★ = best-matching period.</p>'
    )
    html_parts.append(note + '<div class="bar-list">' + "".join(rows) + "</div>")

    # Period reference table
    table_rows: list[str] = []
    for i, (p, dist) in enumerate(zip(periods, dists)):
        label = _fmt_period(str(p.get("period") or p.get("name", f"Period {i + 1}")))
        date_range = _PERIOD_RANGES.get(label.lower(), "—")
        best_cls = ' class="ptbl-best"' if i == best_idx else ""
        table_rows.append(
            f'<tr{best_cls}>'
            f'<td class="ptbl-period">{_esc(label)}</td>'
            f'<td class="ptbl-range">{_esc(date_range)}</td>'
            f'<td class="ptbl-dist">{dist:.5f}</td>'
            f'</tr>'
        )
    html_parts.append(
        f'<table class="period-table">'
        f'<thead><tr>'
        f'<th>Period</th><th>Approx. Years</th><th>Distance</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(table_rows)}</tbody>'
        f'</table>'
    )

    return "".join(html_parts)


# ---------------------------------------------------------------------------
# Key Genetic Signal callout card
# ---------------------------------------------------------------------------

def _key_signal_card(
    by_macro: list[dict],
    by_country: list[dict],
    best_period: str | None,
) -> str:
    """Compact 'Key Genetic Signal' summary card for section C header."""
    items: list[str] = []

    if by_macro and len(by_macro) >= 1:
        m = by_macro[0]
        items.append(
            f'<div class="ks-item">'
            f'<span class="ks-label">Primary signal</span>'
            f'<span class="ks-value">{_esc(str(m.get("macro_region", "")))}'
            f'<span class="ks-pct">{float(m.get("percent", 0)):.1f}%</span></span>'
            f'</div>'
        )
    if by_macro and len(by_macro) >= 2:
        m = by_macro[1]
        items.append(
            f'<div class="ks-item">'
            f'<span class="ks-label">Secondary signal</span>'
            f'<span class="ks-value">{_esc(str(m.get("macro_region", "")))}'
            f'<span class="ks-pct">{float(m.get("percent", 0)):.1f}%</span></span>'
            f'</div>'
        )
    if by_country:
        c = by_country[0]
        items.append(
            f'<div class="ks-item">'
            f'<span class="ks-label">Strongest country proxy</span>'
            f'<span class="ks-value">{_esc(str(c.get("region", "")))}'
            f'<span class="ks-pct">{float(c.get("percent", 0)):.1f}%</span></span>'
            f'</div>'
        )
    if best_period:
        period_label = _fmt_period(str(best_period))
        date_range = _PERIOD_RANGES.get(period_label.lower(), "")
        years_span = (
            f'<span class="ks-years">{_esc(date_range)}</span>'
            if date_range else ""
        )
        items.append(
            f'<div class="ks-item">'
            f'<span class="ks-label">Closest period fit</span>'
            f'<span class="ks-value">{_esc(period_label)}{years_span}</span>'
            f'</div>'
        )

    if not items:
        return ""

    return (
        f'<div class="key-signal-card">'
        f'<div class="ks-title">Key Genetic Signal</div>'
        f'<div class="ks-grid">{"".join(items)}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Interpretation text formatter
# ---------------------------------------------------------------------------

def _find_interpretation_split_pos(html: str) -> int | None:
    """Return the character index at which to split rendered interpretation HTML.

    Strategy (in priority order):
    1. Split immediately before the first <h3 class="interp-section"> that has
       some content (a closed tag) before it — this puts the overview paragraph(s)
       in the preview and all numbered subsections in the collapsible block.
    2. Fallback: split after the 2nd </p> tag.
    Returns None if no suitable split point is found.
    """
    h3_match = re.search(r'<h3 class="interp-section">', html)
    if h3_match:
        pos = h3_match.start()
        content_before = html[:pos]
        if "</p>" in content_before or "</h2>" in content_before:
            return pos

    # Fallback: after 2nd </p>
    start = 0
    count = 0
    while count < 2:
        found = html.find("</p>", start)
        if found == -1:
            return None
        start = found + len("</p>")
        count += 1
    return start if count == 2 else None


def _format_interpretation(text: str | None) -> str:
    if not text or not text.strip():
        return (
            '<div class="interp-placeholder">'
            '<div class="placeholder-icon">&#128214;</div>'
            "<p>Historical interpretation has not yet been added.</p>"
            "<p>Add your narrative to <code>interpretation/interpretation.txt</code>"
            " to populate this section.</p>"
            "</div>"
        )

    # Strip metadata tags (e.g. "run_id: ...") before rendering
    lines = [l for l in text.splitlines() if not l.startswith("run_id:")]
    html: list[str] = []
    in_para = False
    in_list = False
    first_done = False

    _SEP_CHARS = set("━─═—=- ")

    def close_para() -> None:
        nonlocal in_para
        if in_para:
            html.append("</p>")
            in_para = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            html.append("</ul>")
            in_list = False

    for raw in lines:
        stripped = raw.strip()

        if stripped and len(stripped) > 8 and set(stripped) <= _SEP_CHARS:
            close_para(); close_list()
            html.append('<hr class="interp-sep">')
            continue

        if not stripped:
            close_para(); close_list()
            html.append('<div class="interp-space"></div>')
            continue

        if not first_done:
            first_done = True
            close_para(); close_list()
            html.append(f'<h2 class="interp-doc-title">{_esc(stripped)}</h2>')
            continue

        m = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if m and stripped == stripped.upper():
            close_para(); close_list()
            num = _esc(m.group(1))
            title = _esc(m.group(2).title())
            html.append(
                f'<h3 class="interp-section">'
                f'<span class="interp-num">{num}</span>{title}'
                f"</h3>"
            )
            continue

        if re.match(r"^\s*[•·\-\*]\s+", raw):
            close_para()
            if not in_list:
                html.append('<ul class="interp-list">')
                in_list = True
            item_text = re.sub(r"^\s*[•·\-\*]\s*", "", raw)
            html.append(f"<li>{_esc(item_text.strip())}</li>")
            continue

        close_list()
        if not in_para:
            html.append('<p class="interp-para">')
            in_para = True
        else:
            html.append(" ")
        html.append(_esc(stripped))

    close_para(); close_list()

    full_html = "".join(html)
    split_pos = _find_interpretation_split_pos(full_html)
    if split_pos is not None:
        preview_html = full_html[:split_pos]
        hidden_html  = full_html[split_pos:]
        if hidden_html.strip():
            return (
                '<div class="interp-wrap interpretation-block">'
                f'<div class="interpretation-preview">{preview_html}</div>'
                f'<div class="interpretation-hidden">{hidden_html}</div>'
                '<button class="interpretation-toggle" aria-expanded="false">'
                '<span class="toggle-text">Read full interpretation</span>'
                '<span class="toggle-icon">&#9662;</span>'
                "</button>"
                "</div>"
            )
    return f'<div class="interp-wrap">{full_html}</div>'


# ---------------------------------------------------------------------------
# Distance badge
# ---------------------------------------------------------------------------

def _dist_badge(dist: float, quality: str) -> str:
    if dist < 0.03:
        cls = "dist-good"
    elif dist < 0.06:
        cls = "dist-fair"
    else:
        cls = "dist-poor"
    return (
        f'<span class="dist-badge {cls}">'
        f'<span class="dist-dot"></span>'
        f"Distance&nbsp;{dist:.6f}&nbsp;&nbsp;·&nbsp;&nbsp;{_esc(quality)}"
        f"</span>"
    )


# ---------------------------------------------------------------------------
# Executive summary
# ---------------------------------------------------------------------------

def _executive_summary(fr: dict, generic: dict | None) -> str:
    run = fr.get("run", {})
    dist = float(run.get("best_distance", 0))
    quality = str(run.get("distance_quality", ""))
    by_macro = fr.get("by_macro_region", [])
    by_country = fr.get("by_country", [])

    # Always derive the summary from the current run's data.
    # generic_summary.json can be stale (from a previous run) so it is intentionally
    # ignored here.

    parts: list[str] = []
    if by_macro and len(by_macro) >= 2:
        m0, m1 = by_macro[0], by_macro[1]
        parts.append(
            f"Genetic model identifies {m0['percent']:.0f}% {m0['macro_region']} "
            f"and {m1['percent']:.0f}% {m1['macro_region']} ancestry."
        )
    if by_country:
        regions = ", ".join(
            f"{_display_region(c['region'])} ({c['percent']:.0f}%)"
            for c in by_country[:3]
        )
        parts.append(f"Strongest proxy affinity to {regions}.")
    if quality:
        parts.append(f"Genetic distance {dist:.6f} — {quality}.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Full report renderer
# ---------------------------------------------------------------------------

def render_report(
    profile: dict,
    final_report: dict,
    aggregated: dict,
    generic_summary: dict | None,
    period_data: dict | list | None,
    interpretation: str | None,
    theme: str = "dark",
    ydna_interpretation: str | None = None,
) -> str:
    # ── User info ────────────────────────────────────────────────
    display_name = _esc(profile.get("display_name", "User"))
    identity     = _esc(profile.get("identity_context") or "")
    ydna         = _esc(profile.get("ydna_haplogroup") or "")

    # ── Run info ─────────────────────────────────────────────────
    run       = final_report.get("run", {})
    dist      = float(run.get("best_distance", 0))
    quality   = str(run.get("distance_quality", ""))
    prof_name = _esc(run.get("profile") or "")
    run_id    = _esc(str(run.get("run_id", "")))
    stop_rsn  = _esc(str(run.get("stop_reason", "")))
    best_iter = run.get("best_iteration")

    # ── Data ─────────────────────────────────────────────────────
    by_country  = final_report.get("by_country") or aggregated.get("by_country", [])
    by_macro    = (
        final_report.get("by_macro_region")
        or (generic_summary or {}).get("by_macro_region", [])
    )
    top_samples = final_report.get("top_samples") or aggregated.get("top_samples", [])

    # ── Extract best_period ──────────────────────────────────────
    best_period: str | None = None
    if isinstance(period_data, dict):
        best_period = period_data.get("best_period") or None
    if not best_period:
        best_period = (final_report.get("periods") or {}).get("best_period") or None

    # ── CSS + JS ─────────────────────────────────────────────────
    css = get_css(theme)
    js  = get_js()

    # ── Hero chips ───────────────────────────────────────────────
    chips: list[str] = []
    if identity:
        chips.append(f'<span class="chip chip-identity">&#9670;&nbsp;{identity}</span>')
    if ydna:
        chips.append(f'<span class="chip chip-ydna">&#9852;&nbsp;Y&#8209;DNA&nbsp;{ydna}</span>')
    chips.append(f'<span class="chip chip-profile">{prof_name}</span>')
    if best_period:
        chips.append(f'<span class="chip chip-period">&#8982;&nbsp;{_esc(str(best_period))}</span>')

    # ── Charts ───────────────────────────────────────────────────
    # Apply display-layer label remapping, then collapse <1% entries.
    # Internal by_country data (used for calculations) is never modified.
    by_country_disp = [
        {**c, "region": _display_region(c["region"])} for c in by_country
    ]
    by_country_display = _group_small_countries(by_country_disp)
    country_donut = _svg_donut(
        by_country_display, "region", "percent", COUNTRY_COLORS,
        size=200, chart_id="country-donut",
        center_label="Ancestry\nDistribution",
    )
    country_bars = _bar_rows(by_country_display, "region", "percent", COUNTRY_COLORS)

    macro_donut = ""
    if by_macro:
        macro_donut = _svg_donut(
            by_macro, "macro_region", "percent", MACRO_COLORS,
            size=160, chart_id="macro-donut",
            center_label="Macro\nRegion",
        )

    # ── Hero takeaway line ────────────────────────────────────────
    if by_macro and len(by_macro) >= 2:
        _m0 = str(by_macro[0].get("macro_region", ""))
        _m1 = str(by_macro[1].get("macro_region", ""))
        hero_takeaway_html = (
            f'<p class="hero-takeaway">Closest overall fit:&ensp;'
            f'{_esc(_m0)}&thinsp;+&thinsp;{_esc(_m1)}</p>'
        )
    elif by_country_disp:
        _c0 = by_country_disp[0]
        hero_takeaway_html = (
            f'<p class="hero-takeaway">Dominant affinity:&ensp;'
            f'{_esc(str(_c0.get("region", "")))} '
            f'({float(_c0.get("percent", 0)):.1f}%)</p>'
        )
    else:
        hero_takeaway_html = ""

    sample_html        = _sample_cards(top_samples)
    key_signal_html    = _key_signal_card(by_macro, by_country, best_period)
    period_signal_html = _period_signal_card(period_data, best_period)
    # Period card appears BEFORE interpretation narrative; divider always separates it
    period_signal_prefix = (
        '<div class="sub-divider"></div>' + period_signal_html
        if period_signal_html else ""
    )
    period_detail_html = _period_detail_block(period_data, best_period)
    interp_html        = _format_interpretation(interpretation)
    ydna_html          = _format_interpretation(ydna_interpretation) if ydna_interpretation else None
    dist_badge   = _dist_badge(dist, quality)
    exec_summary = _executive_summary(final_report, generic_summary)

    # ── Hero metric row ──────────────────────────────────────────
    _hero_metric_items: list[str] = []
    if by_country_disp:
        _tc = by_country_disp[0]
        _tc_name = str(_tc.get("region", ""))
        _tc_pct  = float(_tc.get("percent", 0))
        _hero_metric_items.append(
            f'<div class="hero-metric">'
            f'<div class="hm-label">Strongest country proxy</div>'
            f'<div class="hm-value">{_esc(_tc_name)}'
            f'&ensp;<span class="hm-pct">{_tc_pct:.1f}%</span></div>'
            f'</div>'
        )
    if best_period:
        _bp_label = _fmt_period(str(best_period))
        _bp_range = _PERIOD_RANGES.get(_bp_label.lower(), "")
        _hero_metric_items.append(
            f'<div class="hero-metric">'
            f'<div class="hm-label">Closest historical period</div>'
            f'<div class="hm-value">{_esc(_bp_label)}'
            + (f'&ensp;<span class="hm-pct">{_esc(_bp_range)}</span>' if _bp_range else "")
            + f'</div></div>'
        )
    if quality:
        _hero_metric_items.append(
            f'<div class="hero-metric">'
            f'<div class="hm-label">Fit quality</div>'
            f'<div class="hm-value">{_esc(quality)}</div>'
            f'</div>'
        )
    hero_metrics_html = (
        f'<div class="hero-metrics">{"".join(_hero_metric_items)}</div>'
        if _hero_metric_items else ""
    )

    # ── Technical meta grid ──────────────────────────────────────
    meta_items: list[str] = [
        f'<div class="meta-item"><span class="meta-label">Run ID</span>'
        f'<span class="meta-value mono">{run_id}</span></div>',
        f'<div class="meta-item"><span class="meta-label">Profile</span>'
        f'<span class="meta-value">{prof_name}</span></div>',
        f'<div class="meta-item"><span class="meta-label">Best Distance</span>'
        f'<span class="meta-value mono">{dist:.6f}</span></div>',
        f'<div class="meta-item"><span class="meta-label">Fit Quality</span>'
        f'<span class="meta-value">{_esc(quality)}</span></div>',
    ]
    if best_iter is not None:
        meta_items.append(
            f'<div class="meta-item"><span class="meta-label">Best Iteration</span>'
            f'<span class="meta-value">{best_iter}</span></div>'
        )
    meta_items.append(
        f'<div class="meta-item"><span class="meta-label">Stop Reason</span>'
        f'<span class="meta-value" style="font-size:0.78rem">{stop_rsn}</span></div>'
    )
    if identity:
        meta_items.append(
            f'<div class="meta-item"><span class="meta-label">Identity Context</span>'
            f'<span class="meta-value">{identity}</span></div>'
        )
    if ydna:
        meta_items.append(
            f'<div class="meta-item"><span class="meta-label">Y-DNA Haplogroup</span>'
            f'<span class="meta-value mono">{ydna}</span></div>'
        )

    # ── Macro region section ─────────────────────────────────────
    macro_section_html = ""
    if macro_donut:
        macro_section_html = f"""
      <div class="sub-divider"></div>
      <div style="display:flex;justify-content:center">
        <div>
          <div class="col-label" style="text-align:center">Macro Region</div>
          {macro_donut}
        </div>
      </div>"""

    # ── TOC links ────────────────────────────────────────────────
    def _toc_link(href: str, letter: str, label: str, active: bool = False) -> str:
        cls = "toc-link active" if active else "toc-link"
        return (
            f'<a href="#{href}" class="{cls}">'
            f'<span class="toc-letter">{letter}</span>'
            f'{label}'
            f'</a>'
        )

    _toc_entries = [
        _toc_link("overview",       "A", "Overview",       active=True),
        _toc_link("ancestry",       "B", "Ancestry"),
        _toc_link("interpretation", "C", "Ancestry Interp."),
        _toc_link("samples",        "D", "Samples"),
        *([_toc_link("ydna",        "F", "Y-DNA Interp.")] if ydna_html else []),
        _toc_link("technical",      "E", "Technical"),
    ]
    toc_links = "\n        ".join(_toc_entries)

    # ── Sidebar distance stat ────────────────────────────────────
    dist_quality_color = (
        "var(--green)" if dist < 0.03
        else "var(--amber)" if dist < 0.06
        else "var(--red)"
    )
    sidebar_stat = (
        f'<div class="sidebar-stat">'
        f'<div class="sidebar-stat-label">Best Distance</div>'
        f'<div class="sidebar-stat-value" style="color:{dist_quality_color}">'
        f'{dist:.6f}&ensp;·&ensp;{_esc(quality)}</div>'
        f'</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="{theme}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Genetic Report &mdash; {display_name}</title>
<style>{css}</style>
</head>
<body>

<div id="chart-tooltip"></div>

<!-- Mobile nav -->
<nav class="mobile-nav">
  <button class="mob-toc-btn" id="mob-toc-btn">Contents</button>
  <span class="mobile-title">{display_name}</span>
  <button class="theme-toggle-btn" aria-label="Toggle theme" title="Toggle dark / light">
    <span class="icon-sun">&#9728;</span><span class="icon-moon">&#9790;</span>
  </button>
</nav>
<div class="mobile-toc-menu" id="mobile-toc-menu">
  <nav class="toc">
    {_toc_link("overview","A","Overview",True)}
    {_toc_link("ancestry","B","Ancestry")}
    {_toc_link("interpretation","C","Ancestry Interp.")}
    {_toc_link("samples","D","Samples")}
    {_toc_link("ydna","F","Y-DNA Interp.") if ydna_html else ""}
    {_toc_link("technical","E","Technical")}
  </nav>
</div>

<div class="page-layout">

  <!-- ── Sidebar ─────────────────────────────────────────────── -->
  <aside class="sidebar">
    <div class="sidebar-inner">
      <div class="sidebar-top-row">
        <div>
          <div class="sidebar-monogram">Ancestry Report</div>
          <div class="sidebar-brand">{display_name}</div>
        </div>
        <button class="theme-toggle-btn" aria-label="Toggle theme" title="Toggle dark / light">
          <span class="icon-sun">&#9728;</span><span class="icon-moon">&#9790;</span>
        </button>
      </div>
      <nav class="toc">
        {toc_links}
      </nav>
      <div class="sidebar-divider"></div>
      <div class="sidebar-footer">
        {sidebar_stat}
      </div>
    </div>
  </aside>

  <!-- ── Main content ─────────────────────────────────────────── -->
  <main class="main-content">

    <!-- ══ A. Hero ══════════════════════════════════════════════ -->
    <section id="overview" class="section hero-section">
      <div class="section-body">
        <div class="hero-eyebrow">Genetic Ancestry Report</div>
        <h1 class="hero-name">{display_name}</h1>
        <div class="hero-ornament"><span>✦ ✦ ✦</span></div>
        <div class="hero-chips">{"".join(chips)}</div>
        <div class="hero-distance-row">{dist_badge}</div>
        {hero_takeaway_html}
        {hero_metrics_html}
        <p class="exec-summary">{_esc(exec_summary)}</p>
      </div>
    </section>

    <!-- ══ B. Ancestry Distribution ═════════════════════════════ -->
    <section id="ancestry" class="section collapsible-section">
      <div class="section-header">
        <div class="section-header-left">
          <div class="section-icon icon-blue">&#9670;</div>
          <div>
            <div class="section-eyebrow">Model-Level Summary</div>
            <div class="section-title">Ancestry Distribution</div>
            <div class="section-sub">by_country is the primary evidence &mdash; ancient populations as genetic proxies</div>
          </div>
        </div>
        <div class="section-badge">B</div>
        <button class="collapsible-toggle" aria-expanded="true"></button>
      </div>
      <div class="section-body">
        <div class="ancestry-layout">
          <div class="ancestry-donut">
            <div class="col-label">Distribution</div>
            {country_donut}
          </div>
          <div class="ancestry-bars">
            <div class="col-label">Ranked Breakdown</div>
            {country_bars}
          </div>
        </div>
        {macro_section_html}
        <p class="section-note">The distribution is centered on Eastern Mediterranean and Southern European populations, with secondary variation reflecting regional admixture.</p>
      </div>
    </section>

    <!-- ══ C. Historical Interpretation ════════════════════════ -->
    <section id="interpretation" class="section collapsible-section">
      <div class="section-header">
        <div class="section-header-left">
          <div class="section-icon icon-gold">&#128214;</div>
          <div>
            <div class="section-title">Ancestry Interpretation</div>
            <div class="section-sub">Bronze Age &rarr; Roman &amp; Byzantine &rarr; Medieval &mdash; ancient populations are genetic proxies only</div>
          </div>
        </div>
        <div class="section-badge">C</div>
        <div class="collapse-hint">Summary shown &mdash; expand for full historical interpretation</div>
        <button class="collapsible-toggle" aria-expanded="true"></button>
      </div>
      <div class="section-body">
        {key_signal_html}
        {period_signal_prefix}
        <div class="sub-divider"></div>
        {interp_html}
      </div>
    </section>

    <!-- ══ D. Sample-Level Proxies ══════════════════════════════ -->
    <section id="samples" class="section collapsible-section section-divider-top">
      <div class="section-header">
        <div class="section-header-left">
          <div class="section-icon icon-teal">&#9652;</div>
          <div>
            <div class="section-eyebrow">Raw Genetic Proxies</div>
            <div class="section-title">Sample-Level Proxies</div>
            <div class="section-sub">Top contributing reference populations &mdash; supporting detail below ancestry distribution</div>
          </div>
        </div>
        <div class="section-badge">D</div>
        <button class="collapsible-toggle" aria-expanded="true"></button>
      </div>
      <div class="section-body">
        <p class="section-note">These samples represent closest-fit ancient and historical proxies and should be interpreted as population approximations rather than direct ancestry.</p>
        {sample_html}
      </div>
    </section>

    <!-- ══ F. Y-DNA (Paternal Line) ═════════════════════════════ -->
    {"" if not ydna_html else f"""
    <section id="ydna" class="section collapsible-section section-divider-top">
      <div class="section-header">
        <div class="section-header-left">
          <div class="section-icon icon-gold">&#129516;</div>
          <div>
            <div class="section-title">Y&#8209;DNA Interpretation</div>
            <div class="section-sub">Paternal lineage analysis &mdash; single line only, does not represent full ancestry</div>
          </div>
        </div>
        <div class="section-badge">F</div>
        <button class="collapsible-toggle" aria-expanded="true"></button>
      </div>
      <div class="section-body">
        {ydna_html}
      </div>
    </section>"""}

    <!-- ══ E. Technical Appendix ════════════════════════════════ -->
    <section id="technical" class="section collapsible-section collapsed">
      <div class="section-header">
        <div class="section-header-left">
          <div class="section-icon icon-gray">&#9881;</div>
          <div>
            <div class="section-title">Technical Appendix</div>
            <div class="section-sub">Run metadata and artifact references</div>
          </div>
        </div>
        <div class="section-badge">E</div>
        <button class="collapsible-toggle" aria-expanded="false"></button>
      </div>
      <div class="section-body">
        <div class="meta-grid">{"".join(meta_items)}</div>
        <details class="appendix-details">
          <summary class="appendix-summary">Period Diagnostics</summary>
          <div class="appendix-details-body">
            {period_detail_html}
          </div>
        </details>
      </div>
    </section>

    <footer>
      Generated from run <code>{run_id}</code><br>
      All ancient reference samples are genetic proxies only.
      Results do not constitute ethnic or genealogical determinations.
    </footer>

  </main>
</div>

<script>{js}</script>
</body>
</html>
"""
