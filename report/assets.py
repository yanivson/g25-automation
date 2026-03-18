"""report/assets.py — Embedded CSS and JavaScript for the standalone HTML report.

Design direction: "The Gilded Archive"
- Palatino/Georgia for display/prose; Optima/Candara for UI labels; monospace for data
- Very dark navy (#06060c) with warm amber gold (#c8924a) accents
- Animated grain texture, section rise animations, pulsing distance badge
- Sticky sidebar with active indicator bar, mobile fallback nav
- SVG donut charts with glow halo + hover brightness
- Animated horizontal bars with shimmer sweep
- Sample cards with slide-on-hover
"""

from __future__ import annotations

from .theme import DARK_VARS, LIGHT_VARS


def get_css(theme: str = "dark") -> str:
    """Return the complete embedded CSS. theme: 'dark' | 'light' | 'auto'.

    Both dark and light palettes are always embedded so the in-page toggle
    button can switch themes at runtime without a page reload.
    """

    # html[data-theme='X'] has specificity (0,1,1) which always beats :root (0,1,0).
    # This guarantees JS toggle overrides the default palette without cascade fights.
    if theme == "light":
        root_vars = (
            f":root {{{LIGHT_VARS}}}"
            f"\nhtml[data-theme='dark']  {{{DARK_VARS}}}"
            f"\nhtml[data-theme='light'] {{{LIGHT_VARS}}}"
        )
    elif theme == "auto":
        root_vars = (
            f":root {{{DARK_VARS}}}"
            "\n@media (prefers-color-scheme: light) {"
            f"  :root {{{LIGHT_VARS}}}"
            "\n}"
            f"\nhtml[data-theme='dark']  {{{DARK_VARS}}}"
            f"\nhtml[data-theme='light'] {{{LIGHT_VARS}}}"
        )
    else:  # dark (default)
        root_vars = (
            f":root {{{DARK_VARS}}}"
            f"\nhtml[data-theme='dark']  {{{DARK_VARS}}}"
            f"\nhtml[data-theme='light'] {{{LIGHT_VARS}}}"
        )

    return root_vars + r"""

/* ── Fonts ───────────────────────────────────────────────────── */
/* System font stacks chosen for premium feel without external load */

/* ── Reset ───────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 16px; scroll-behavior: smooth; }
body {
  font-family: var(--font-ui);
  background: var(--bg);
  color: var(--ink);
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  overflow-x: hidden;
}

/* ── Film-grain texture ──────────────────────────────────────── */
/* Animated SVG noise overlay — adds tactile depth to dark surfaces */
body::before {
  content: '';
  position: fixed;
  top: -50%; left: -50%;
  width: 200%; height: 200%;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='400'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.72' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='400' height='400' filter='url(%23n)'/%3E%3C/svg%3E");
  opacity: 0.022;
  pointer-events: none;
  z-index: 9000;
  will-change: transform;
  animation: grain 0.9s steps(1) infinite;
}
@keyframes grain {
  0%,100% { transform: translate(0,0); }
  11%  { transform: translate(-3%,-4%); }
  22%  { transform: translate(-8%, 3%); }
  33%  { transform: translate( 4%,-8%); }
  44%  { transform: translate(-4%,12%); }
  55%  { transform: translate(-9%, 4%); }
  66%  { transform: translate(12%, 0%); }
  77%  { transform: translate( 0%, 8%); }
  88%  { transform: translate(-12%,0%); }
}

/* ── Tooltip ─────────────────────────────────────────────────── */
#chart-tooltip {
  display: none;
  position: fixed;
  z-index: 8000;
  background: var(--bg-3);
  color: var(--ink);
  border: 1px solid var(--border-3);
  border-radius: 8px;
  padding: 0.4rem 0.85rem;
  font-family: var(--font-ui);
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.3px;
  pointer-events: none;
  white-space: nowrap;
  box-shadow: var(--shadow-lg);
}
#chart-tooltip strong { color: var(--gold-2); }

/* ── Page layout ─────────────────────────────────────────────── */
.page-layout {
  display: flex;
  min-height: 100vh;
  align-items: flex-start;
}

/* ── Sidebar ─────────────────────────────────────────────────── */
.sidebar {
  width: 220px;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
  background: var(--bg-1);
  border-right: 1px solid var(--border);
  box-shadow: inset -1px 0 0 rgba(200,146,74,0.07);
  display: flex;
  flex-direction: column;
}
.sidebar::-webkit-scrollbar { width: 3px; }
.sidebar::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 4px; }

.sidebar-inner {
  padding: 2rem 1.2rem 1.5rem;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.sidebar-monogram {
  font-family: var(--font-display);
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 4px;
  color: var(--gold);
  opacity: 0.65;
  margin-bottom: 0.25rem;
}

.sidebar-brand {
  font-family: var(--font-display);
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.3;
}

.toc { display: flex; flex-direction: column; gap: 1px; flex: 1; }

.toc-link {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.52rem 0.6rem;
  border-radius: 8px;
  font-family: var(--font-ui);
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--ink-3);
  text-decoration: none;
  position: relative;
  transition: background 0.16s ease, color 0.16s ease;
}
.toc-link:hover { background: var(--gold-dim); color: var(--ink-2); }
.toc-link.active {
  background: var(--gold-dim2);
  color: var(--gold-2);
  font-weight: 600;
}
/* Active left-rail indicator */
.toc-link.active::before {
  content: '';
  position: absolute;
  left: -0.55rem;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 55%;
  background: var(--gold);
  border-radius: 0 3px 3px 0;
}

.toc-letter {
  width: 21px; height: 21px;
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-display);
  font-size: 0.65rem;
  font-weight: 800;
  background: var(--bg-3);
  color: var(--ink-3);
  flex-shrink: 0;
  transition: background 0.16s, color 0.16s;
}
.toc-link.active .toc-letter {
  background: var(--gold-dim2);
  color: var(--gold);
}

.sidebar-divider { height: 1px; background: var(--border); margin: 1.2rem 0; }

.sidebar-footer { margin-top: auto; }

.sidebar-stat {
  padding: 0.7rem 0.75rem;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.sidebar-stat-label {
  font-family: var(--font-display);
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.8px;
  color: var(--ink-3);
  margin-bottom: 0.22rem;
}
.sidebar-stat-value {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  color: var(--green);
  font-weight: 600;
  letter-spacing: 0.3px;
}

/* ── Main content ────────────────────────────────────────────── */
.main-content { flex: 1; min-width: 0; max-width: 860px; }

/* ── Mobile nav ──────────────────────────────────────────────── */
.mobile-nav {
  display: none;
  align-items: center;
  gap: 0.75rem;
  padding: 0.7rem 1rem;
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 500;
}
.mobile-title {
  font-family: var(--font-display);
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--ink);
  flex: 1;
}
.mob-toc-btn {
  background: var(--bg-2);
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 0.3rem 0.65rem;
  font-size: 0.75rem;
  color: var(--ink-2);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  font-family: var(--font-ui);
}
.mob-toc-btn:hover { background: var(--bg-3); color: var(--ink); }

.mobile-toc-menu {
  display: none;
  position: fixed;
  top: 48px; left: 0; right: 0;
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
  padding: 0.7rem;
  z-index: 499;
  box-shadow: var(--shadow-lg);
}
.mobile-toc-menu.open { display: block; }
.mobile-toc-menu .toc { flex-direction: row; flex-wrap: wrap; gap: 4px; }
.mobile-toc-menu .toc-link { padding: 0.38rem 0.65rem; font-size: 0.77rem; }
.mobile-toc-menu .toc-link.active::before { display: none; }

@media (max-width: 900px) {
  .sidebar { display: none; }
  .mobile-nav { display: flex; }
  .main-content { max-width: 100%; padding-bottom: 3rem; }
}

/* ── Section cards ───────────────────────────────────────────── */
.section {
  margin: 1.5rem 1.5rem 0 1.5rem;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 20px;
  overflow: hidden;
  animation: rise 0.65s cubic-bezier(0.16, 1, 0.3, 1) both;
  box-shadow: 0 4px 28px rgba(0,0,0,0.22), 0 1px 0 rgba(255,255,255,0.018) inset;
}
.section:nth-child(1) { animation-delay: 0.00s; }
.section:nth-child(2) { animation-delay: 0.07s; }
.section:nth-child(3) { animation-delay: 0.14s; }
.section:nth-child(4) { animation-delay: 0.21s; }
.section:nth-child(5) { animation-delay: 0.28s; }

@keyframes rise {
  from { opacity: 0; transform: translateY(18px); }
  to   { opacity: 1; transform: translateY(0); }
}

@media (max-width: 900px) {
  .section { margin: 1rem 0.75rem 0 0.75rem; border-radius: 14px; }
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.1rem 1.5rem;
  background: var(--bg-3);
  border-bottom: 1px solid var(--border);
  position: relative;
  overflow: hidden;
}

/* Large faint letter badge — gives depth and editorial feel */
.section-badge {
  position: absolute;
  right: 1rem;
  top: 50%;
  transform: translateY(-50%);
  font-family: var(--font-serif);
  font-size: 4.5rem;
  font-weight: 900;
  color: var(--gold);
  opacity: 0.045;
  user-select: none;
  pointer-events: none;
  line-height: 1;
  letter-spacing: -3px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  position: relative;
  z-index: 1;
}

.section-icon {
  width: 36px; height: 36px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1rem;
  flex-shrink: 0;
}
.icon-gold  { background: var(--gold-dim2); color: var(--gold-2); border: 1px solid rgba(200,146,74,0.22); }
.icon-blue  { background: var(--blue-dim);  color: var(--blue);   border: 1px solid rgba(74,142,245,0.22); }
.icon-green { background: var(--green-dim); color: var(--green);  border: 1px solid rgba(34,197,147,0.22); }
.icon-gray  { background: var(--bg-4);      color: var(--ink-3);  border: 1px solid var(--border-2); }

.section-eyebrow {
  font-family: var(--font-ui);
  font-size: 0.60rem;
  font-weight: 500;
  color: var(--ink-3);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  margin-bottom: 0.3rem;
}
.section-note {
  font-size: 0.78rem;
  color: var(--ink-3);
  margin-top: 1rem;
  padding-top: 0.75rem;
  border-top: 1px solid rgba(255,255,255,0.06);
  font-style: italic;
}
.collapse-hint {
  display: none;
  font-size: 0.72rem;
  color: var(--ink-3);
  font-style: italic;
  margin-right: 0.5rem;
  align-self: center;
}
.collapsible-section.collapsed .collapse-hint { display: block; }
.section-title {
  font-family: var(--font-display);
  font-size: 0.95rem;
  font-weight: 650;
  color: var(--ink);
  letter-spacing: 0.15px;
}
.section-sub { font-size: 0.72rem; color: var(--ink-3); margin-top: 1px; letter-spacing: 0.2px; }
.section-divider-top {
  border-top: 1px solid rgba(255,255,255,0.06);
  margin-top: 2rem;
}

.collapsible-toggle {
  background: none;
  border: 1px solid var(--border-2);
  cursor: pointer;
  color: var(--ink-3);
  font-size: 0.72rem;
  padding: 0.28rem 0.6rem;
  border-radius: 8px;
  font-family: var(--font-ui);
  letter-spacing: 0.2px;
  transition: all 0.15s;
  position: relative;
  z-index: 1;
}
.collapsible-toggle:hover { background: var(--bg-4); color: var(--ink-2); border-color: var(--border-3); }
.collapsible-section .collapsible-toggle::after { content: "collapse ▲"; }
.collapsible-section.collapsed .collapsible-toggle::after { content: "expand ▼"; }
.collapsible-section.collapsed .section-body { display: none; }

.section-body { padding: 1.75rem; }

/* ── Hero section ────────────────────────────────────────────── */
.hero-section {
  margin: 0;
  border-radius: 0;
  border-left: none; border-right: none; border-top: none;
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
  /* Radial light source — premium depth */
  background-image:
    radial-gradient(ellipse 80% 55% at 50% -10%, rgba(200,146,74,0.055) 0%, transparent 65%),
    radial-gradient(ellipse 55% 35% at 15% 110%, rgba(74,142,245,0.03) 0%, transparent 55%);
}
.hero-section .section-body { padding: 3.5rem 2.5rem 3.25rem; }

.hero-eyebrow {
  font-family: var(--font-display);
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 5px;
  color: var(--gold);
  opacity: 0.8;
  margin-bottom: 1.1rem;
}

.hero-name {
  font-family: var(--font-serif);
  font-size: clamp(2.8rem, 6vw, 4.5rem);
  font-weight: 300;
  letter-spacing: 3px;
  color: var(--ink);
  line-height: 1.1;
}

/* Decorative ornament — thin gold rule with central diamond */
.hero-ornament {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 0 1.2rem;
  color: var(--gold);
  opacity: 0.35;
  max-width: 340px;
}
.hero-ornament::before,
.hero-ornament::after {
  content: '';
  flex: 1;
  height: 1px;
  background: currentColor;
}
.hero-ornament span { font-size: 0.6rem; letter-spacing: 3px; flex-shrink: 0; }

.hero-chips { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.5rem; }

.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.75rem;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 500;
  font-family: var(--font-ui);
  letter-spacing: 0.25px;
}
.chip-identity { background: rgba(200,146,74,0.10); color: var(--gold-2); border: 1px solid rgba(200,146,74,0.22); }
.chip-ydna     { background: rgba(74,142,245,0.09); color: var(--blue);   border: 1px solid rgba(74,142,245,0.20); }
.chip-profile  { background: var(--bg-3); color: var(--ink-2); border: 1px solid var(--border-2); font-family: var(--font-mono); font-size: 0.7rem; }
.chip-period   { background: rgba(155,114,245,0.09); color: #b89fff; border: 1px solid rgba(155,114,245,0.22); }

.hero-distance-row { margin-bottom: 1.75rem; }

.dist-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.52rem 1.15rem;
  border-radius: 999px;
  font-size: 0.86rem;
  font-weight: 600;
  font-family: var(--font-ui);
  letter-spacing: 0.2px;
}
.dist-good  { background: var(--green-dim);  color: var(--green); border: 1px solid rgba(34,197,147,0.28); }
.dist-fair  { background: var(--amber-dim);  color: var(--amber); border: 1px solid rgba(230,160,30,0.28); }
.dist-poor  { background: var(--red-dim);    color: var(--red);   border: 1px solid rgba(224,85,85,0.28); }

.dist-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.dist-good .dist-dot { animation: pulse-ok 2.8s ease-in-out infinite; }

@keyframes pulse-ok {
  0%,100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34,197,147,0.45); }
  50%      { opacity: 0.75; box-shadow: 0 0 0 5px rgba(34,197,147,0); }
}

.exec-summary {
  font-size: 0.93rem;
  color: var(--ink-2);
  line-height: 1.85;
  max-width: 600px;
  padding-left: 1.1rem;
  border-left: 2px solid rgba(200,146,74,0.3);
  font-family: var(--font-ui);
}

/* ── Layout helpers ──────────────────────────────────────────── */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2.5rem;
}
@media (max-width: 680px) { .two-col { grid-template-columns: 1fr; gap: 2rem; } }

.col-label {
  font-family: var(--font-display);
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2.2px;
  color: var(--ink-3);
  margin-bottom: 1.2rem;
}

.sub-divider {
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, var(--border-2) 30%, var(--border-2) 70%, transparent 100%);
  margin: 2rem 0;
}

/* ── SVG Donut chart ─────────────────────────────────────────── */
.donut-outer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
}

/* Subtle glow halo around the donut ring */
.donut-ring-wrap {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}
.donut-ring-wrap::before {
  content: '';
  position: absolute;
  inset: -10px;
  border-radius: 50%;
  background: radial-gradient(ellipse at center, rgba(200,146,74,0.05) 0%, transparent 70%);
  pointer-events: none;
}

.donut-chart { overflow: visible; }

.donut-seg {
  cursor: pointer;
  transition: opacity 0.16s ease, filter 0.16s ease;
}
.donut-seg:hover {
  opacity: 0.86;
  filter: brightness(1.2) drop-shadow(0 0 5px currentColor);
}

.donut-center-val {
  font-family: var(--font-display);
  font-size: 1.2rem;
  font-weight: 700;
  fill: var(--ink);
  letter-spacing: -0.5px;
}
.donut-center-lbl {
  font-family: var(--font-display);
  font-size: 0.6rem;
  fill: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 1.5px;
}

.donut-legend { display: flex; flex-direction: column; gap: 0.5rem; width: 100%; }

.leg-item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.28rem 0.45rem;
  border-radius: 7px;
  cursor: default;
  transition: background 0.13s;
}
.leg-item:hover { background: var(--bg-3); }

.leg-dot { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }

.leg-text {
  flex: 1;
  font-family: var(--font-ui);
  font-size: 0.84rem;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.leg-pct {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--ink-2);
  min-width: 42px;
  text-align: right;
}

/* ── Horizontal bars ─────────────────────────────────────────── */
.bar-list { display: flex; flex-direction: column; gap: 0.82rem; }

.bar-row {
  display: grid;
  grid-template-columns: 110px 1fr 52px;
  align-items: center;
  gap: 0.7rem;
}

.bar-label {
  font-family: var(--font-ui);
  font-size: 0.84rem;
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bar-track {
  background: var(--bg-4);
  border-radius: 6px;
  height: 11px;
  overflow: hidden;
  position: relative;
}

.bar-fill {
  height: 100%;
  border-radius: 6px;
  width: 0;
  transition: width 1.1s cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
  overflow: hidden;
}

/* Shimmer sweep after bar animates in */
.bar-fill::after {
  content: '';
  position: absolute;
  top: 0; left: -70%;
  width: 55%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent);
  opacity: 0;
  animation: shimmer-sweep 2s 1.25s ease-in-out forwards;
}
@keyframes shimmer-sweep {
  from { left: -70%; opacity: 1; }
  to   { left: 115%; opacity: 0; }
}

.bar-pct {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--ink-2);
  text-align: right;
}

/* Top result in bar lists gets stronger label weight */
.bar-list .bar-row:first-child .bar-label {
  font-weight: 650;
  color: var(--ink);
}
.bar-list .bar-row:first-child .bar-pct {
  color: var(--ink);
}

/* ── Sample cards ────────────────────────────────────────────── */
.sample-list { display: flex; flex-direction: column; gap: 0.55rem; }

.sample-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.55rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--bg-3);
  transition: background 0.14s, border-color 0.14s, transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.sample-card:hover {
  background: var(--bg-4);
  border-color: var(--border-2);
  transform: translateX(4px);
}

.sample-rank {
  width: 28px; height: 28px;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-display);
  font-size: 0.72rem;
  font-weight: 800;
  color: #fff;
  flex-shrink: 0;
}

.sample-body { flex: 1; min-width: 0; }

.sample-name {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 0.3rem;
  letter-spacing: 0.3px;
}

.sample-mini-track { background: var(--bg); border-radius: 3px; height: 3px; overflow: hidden; }

.sample-mini-fill {
  height: 100%;
  border-radius: 3px;
  width: 0;
  transition: width 1.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.sample-pct {
  font-family: var(--font-mono);
  font-size: 0.92rem;
  font-weight: 750;
  color: var(--ink);
  min-width: 46px;
  text-align: right;
}

/* ── Interpretation text ─────────────────────────────────────── */
.interp-wrap { color: var(--ink); line-height: 1.9; }

.interp-doc-title {
  font-family: var(--font-serif);
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--gold-2);
  margin-bottom: 0.28rem;
  letter-spacing: 0.4px;
}

.interp-meta {
  font-family: var(--font-mono);
  font-size: 0.74rem;
  color: var(--ink-3);
  letter-spacing: 0.4px;
  margin-bottom: 1.1rem;
}

.interp-sep {
  border: none;
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, var(--border-2) 25%, var(--border-2) 75%, transparent 100%);
  margin: 1.5rem 0;
}

.interp-section {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  margin: 2.4rem 0 0.75rem;
  font-family: var(--font-display);
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2.8px;
  color: var(--gold);
  padding-bottom: 0.5rem;
  border-bottom: 1px solid rgba(200,146,74,0.12);
}

.interp-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px; height: 22px;
  border-radius: 6px;
  background: var(--gold-dim2);
  border: 1px solid rgba(200,146,74,0.22);
  font-family: var(--font-display);
  font-size: 0.67rem;
  color: var(--gold-2);
  flex-shrink: 0;
}

.interp-para {
  font-family: var(--font-serif);
  font-size: 0.97rem;
  color: var(--ink);
  margin: 0 0 1.35rem;
  max-width: 660px;
  letter-spacing: 0.2px;
  line-height: 1.95;
}

.interp-list {
  margin: 0.4rem 0 0.9rem 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.28rem;
  list-style: none;
}
.interp-list li {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  color: var(--ink-2);
  padding-left: 1rem;
  position: relative;
}
.interp-list li::before {
  content: '▸';
  position: absolute;
  left: 0;
  color: var(--gold);
  opacity: 0.55;
}

.interp-space { height: 0.28rem; }

.interp-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 2rem;
  background: var(--bg-3);
  border: 1px dashed var(--border-2);
  border-radius: 14px;
  color: var(--ink-3);
  text-align: center;
  gap: 0.65rem;
}
.placeholder-icon { font-size: 2.2rem; opacity: 0.3; }
.interp-placeholder p { font-size: 0.88rem; font-family: var(--font-ui); }
.interp-placeholder code {
  background: var(--bg-4);
  border: 1px solid var(--border-2);
  padding: 0.18rem 0.45rem;
  border-radius: 5px;
  font-family: var(--font-mono);
  font-size: 0.79rem;
  color: var(--ink-2);
}

/* ── Period chart ────────────────────────────────────────────── */
.period-note {
  font-family: var(--font-ui);
  font-size: 0.76rem;
  color: var(--ink-3);
  margin-bottom: 1.25rem;
  font-style: italic;
}

.no-data {
  font-family: var(--font-ui);
  font-size: 0.88rem;
  color: var(--ink-3);
  font-style: italic;
  padding: 2rem;
  text-align: center;
  background: var(--bg-3);
  border-radius: 12px;
  border: 1px dashed var(--border-2);
}

/* ── Macro region breakdown ──────────────────────────────────── */
.macro-table { display: flex; flex-direction: column; margin-top: 0.5rem; }
.macro-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}
.macro-row:last-child { border-bottom: none; }
.macro-name { font-family: var(--font-ui); font-size: 0.86rem; color: var(--ink); }
.macro-sub  { font-family: var(--font-ui); font-size: 0.72rem; color: var(--ink-3); margin-top: 1px; }
.macro-pct  { font-family: var(--font-mono); font-size: 0.92rem; font-weight: 700; color: var(--ink-2); }

/* ── Technical appendix ──────────────────────────────────────── */
.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 0.75rem;
}

.meta-item {
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem 0.95rem;
  transition: border-color 0.15s;
}
.meta-item:hover { border-color: var(--border-3); }

.meta-label {
  display: block;
  font-family: var(--font-display);
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.8px;
  color: var(--ink-3);
  margin-bottom: 0.28rem;
}
.meta-value {
  display: block;
  font-family: var(--font-ui);
  font-size: 0.87rem;
  font-weight: 500;
  color: var(--ink);
}
.meta-value.mono {
  font-family: var(--font-mono);
  font-size: 0.79rem;
  letter-spacing: 0.3px;
}

/* ── Footer ──────────────────────────────────────────────────── */
footer {
  text-align: center;
  padding: 2rem 1.5rem 3.5rem;
  margin: 1.5rem 1.5rem 0;
  font-family: var(--font-ui);
  font-size: 0.74rem;
  color: var(--ink-3);
  border-top: 1px solid var(--border);
  line-height: 1.9;
  letter-spacing: 0.2px;
}
footer code {
  font-family: var(--font-mono);
  background: var(--bg-3);
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  color: var(--ink-2);
  font-size: 0.8rem;
}

/* ── Ancestry layout — donut LEFT + bars RIGHT ───────────────── */
.ancestry-layout {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2.5rem;
  align-items: start;
}
.ancestry-donut { min-width: 0; }
.ancestry-bars  { min-width: 0; }
@media (max-width: 680px) {
  .ancestry-layout { grid-template-columns: 1fr; gap: 2rem; }
}

/* ── Period best-fit callout ─────────────────────────────────── */
.period-best-callout {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.85rem 1.2rem;
  margin-bottom: 1.5rem;
  background: rgba(155,114,245,0.07);
  border: 1px solid rgba(155,114,245,0.20);
  border-radius: 12px;
}
.period-best-label {
  font-family: var(--font-display);
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2.5px;
  color: var(--ink-3);
  white-space: nowrap;
}
.period-best-value {
  font-family: var(--font-display);
  font-size: 1.05rem;
  font-weight: 650;
  color: #b898ff;
  letter-spacing: 0.2px;
}

/* ── Period reference table ──────────────────────────────────── */
.period-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1.75rem;
  font-family: var(--font-ui);
  font-size: 0.83rem;
}
.period-table thead tr {
  background: var(--bg-3);
  border-bottom: 1px solid var(--border-2);
}
.period-table th {
  padding: 0.5rem 0.85rem;
  text-align: left;
  font-family: var(--font-display);
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.8px;
  color: var(--ink-3);
}
.period-table td {
  padding: 0.55rem 0.85rem;
  border-bottom: 1px solid var(--border);
  color: var(--ink-2);
}
.period-table tbody tr:last-child td { border-bottom: none; }
.period-table tbody tr:hover td { background: var(--bg-3); }
.period-table tr.ptbl-best td { color: var(--ink); }
.ptbl-period { font-weight: 600; color: var(--ink); }
.ptbl-range  { color: var(--ink-3); font-size: 0.78rem; }
.ptbl-dist   { font-family: var(--font-mono); font-size: 0.78rem; text-align: right; }

/* ── Sample meta (country + period label) ────────────────────── */
.sample-meta {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  margin: 0.12rem 0 0.3rem;
  font-size: 0.73rem;
}
.sample-country {
  font-family: var(--font-display);
  font-weight: 650;
  letter-spacing: 0.2px;
}
.sample-period {
  font-family: var(--font-ui);
  color: var(--ink-3);
  font-size: 0.71rem;
}
.sample-note {
  font-family: var(--font-ui);
  font-size: 0.76rem;
  color: var(--ink-3);
  font-style: italic;
  margin-bottom: 1.2rem;
}
.sample-note em { font-style: normal; color: var(--gold); }

/* ── Key Genetic Signal card ─────────────────────────────────── */
.key-signal-card {
  background: var(--bg-3);
  border: 1px solid var(--border-2);
  border-radius: 14px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 2rem;
}

.ks-title {
  font-family: var(--font-display);
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 3px;
  color: var(--gold);
  opacity: 0.9;
  margin-bottom: 1rem;
}

.ks-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem 2.5rem;
}
@media (max-width: 600px) { .ks-grid { grid-template-columns: 1fr; } }

.ks-item {
  display: flex;
  flex-direction: column;
  gap: 0.18rem;
}

.ks-label {
  font-family: var(--font-display);
  font-size: 0.58rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--ink-3);
}

.ks-value {
  font-family: var(--font-ui);
  font-size: 0.93rem;
  font-weight: 500;
  color: var(--ink);
  display: flex;
  align-items: baseline;
  gap: 0.55rem;
}

.ks-pct {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--gold-2);
}

.ks-years {
  font-family: var(--font-mono);
  font-size: 0.73rem;
  color: var(--ink-3);
}

/* ── Period signal card (compact, shown inside Interpretation) ── */
.period-signal-card {
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-left: 3px solid rgba(155,114,245,0.45);
  border-radius: 12px;
  padding: 1rem 1.25rem;
}

.period-signal-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.65rem;
}
.period-signal-icon {
  font-size: 0.9rem;
  color: #b898ff;
  opacity: 0.8;
}
.period-signal-title {
  font-family: var(--font-display);
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2.5px;
  color: var(--ink-3);
}

.period-signal-main {
  display: flex;
  align-items: baseline;
  gap: 0.85rem;
  margin-bottom: 0.7rem;
}
.period-signal-value {
  font-family: var(--font-display);
  font-size: 1.2rem;
  font-weight: 650;
  color: #b898ff;
  letter-spacing: 0.2px;
}
.period-signal-years {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--ink-3);
}

.period-signal-note {
  font-family: var(--font-ui);
  font-size: 0.8rem;
  color: var(--ink-3);
  line-height: 1.6;
  margin: 0;
  font-style: italic;
}

/* ── Appendix details/summary (period subsection) ────────────── */
.appendix-details {
  margin-top: 1.5rem;
  border-top: 1px solid var(--border);
  padding-top: 0.1rem;
}
.appendix-summary {
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.85rem 0;
  font-family: var(--font-display);
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2.2px;
  color: var(--ink-3);
  user-select: none;
  transition: color 0.15s;
}
.appendix-summary::-webkit-details-marker { display: none; }
.appendix-summary::after {
  content: "expand ▼";
  font-size: 0.65rem;
  letter-spacing: 0.5px;
  color: var(--ink-3);
  transition: color 0.15s;
}
details[open] .appendix-summary::after { content: "collapse ▲"; }
.appendix-summary:hover { color: var(--ink-2); }
.appendix-summary:hover::after { color: var(--ink-2); }
.appendix-details-body { padding-top: 1rem; }

/* ── Teal icon (samples section) ────────────────────────────── */
.icon-teal {
  background: rgba(34,197,147,0.09);
  color: var(--green);
  border: 1px solid rgba(34,197,147,0.22);
}

/* ── Hero takeaway line ──────────────────────────────────────── */
.hero-takeaway {
  font-family: var(--font-display);
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--gold-2);
  letter-spacing: 0.4px;
  margin-bottom: 1.1rem;
  opacity: 0.92;
}

/* ── Hero metric row ─────────────────────────────────────────── */
.hero-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.1rem;
  margin: 0.6rem 0 1.2rem;
}
.hero-metric {
  display: flex;
  flex-direction: column;
  gap: 0.18rem;
  padding: 0.45rem 0.8rem;
  border-radius: 8px;
  background: rgba(200,146,74,0.07);
  border: 1px solid rgba(200,146,74,0.18);
  min-width: 130px;
}
.hm-label {
  font-family: var(--font-display);
  font-size: 0.67rem;
  font-weight: 600;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: var(--ink-3);
}
.hm-value {
  font-family: var(--font-display);
  font-size: 0.88rem;
  font-weight: 650;
  color: var(--ink);
}
.hm-pct {
  font-size: 0.78rem;
  color: var(--ink-3);
  font-weight: 400;
}

/* ── Interpretation collapse / read-more ─────────────────────── */
.interpretation-block { }

.interpretation-hidden {
  height: 0;
  overflow: hidden;
  /* height set by JS for smooth animation */
}

.interpretation-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 1.5rem;
  padding: 0.52rem 1.1rem;
  border: 1px solid var(--border-2);
  border-radius: 9px;
  background: var(--bg-3);
  color: var(--gold-2);
  font-family: var(--font-display);
  font-size: 0.73rem;
  font-weight: 650;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.interpretation-toggle:hover {
  background: var(--gold-dim);
  border-color: rgba(200,146,74,0.32);
  color: var(--gold-3);
}
.interpretation-toggle:focus-visible {
  outline: 2px solid var(--gold);
  outline-offset: 2px;
}
.toggle-icon {
  font-size: 0.68rem;
  opacity: 0.7;
  transition: transform 0.25s;
}
.interpretation-toggle[aria-expanded="true"] .toggle-icon {
  transform: rotate(180deg);
}

/* ── Theme toggle button ─────────────────────────────────────── */
/* Appears in sidebar header (desktop) and mobile nav (mobile) */
.theme-toggle-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid var(--border-2);
  background: var(--bg-3);
  color: var(--ink-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.9rem;
  flex-shrink: 0;
  transition: background 0.16s, border-color 0.16s, color 0.16s;
}
.theme-toggle-btn:hover {
  background: var(--bg-4);
  border-color: var(--gold);
  color: var(--gold);
}
.theme-toggle-btn:active { transform: scale(0.92); }

/* Icon visibility by theme */
html[data-theme="dark"]  .theme-toggle-btn .icon-sun  { display: inline; }
html[data-theme="dark"]  .theme-toggle-btn .icon-moon { display: none;   }
html[data-theme="light"] .theme-toggle-btn .icon-sun  { display: none;   }
html[data-theme="light"] .theme-toggle-btn .icon-moon { display: inline; }
/* Default (dark) */
.icon-sun  { display: inline; }
.icon-moon { display: none;   }

/* Sidebar header row: brand + toggle side by side */
.sidebar-top-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
  padding-bottom: 1.2rem;
  border-bottom: 1px solid var(--border);
}
"""


def get_js() -> str:
    return r"""
(function () {
  'use strict';

  // ── Tooltip ─────────────────────────────────────────────────
  var tip = document.getElementById('chart-tooltip');

  function showTip(e, html) {
    tip.innerHTML = html;
    tip.style.display = 'block';
    moveTip(e);
  }
  function moveTip(e) {
    var x = e.clientX + 14, y = e.clientY - 10;
    // Keep within viewport
    var tw = tip.offsetWidth;
    if (x + tw > window.innerWidth - 8) x = e.clientX - tw - 8;
    tip.style.left = x + 'px';
    tip.style.top  = y + 'px';
  }
  function hideTip() { tip.style.display = 'none'; }

  // ── Donut segments ───────────────────────────────────────────
  document.querySelectorAll('.donut-seg').forEach(function (seg) {
    seg.addEventListener('mouseenter', function (e) {
      showTip(e, '<strong>' + seg.getAttribute('data-label') + '</strong>&ensp;' + seg.getAttribute('data-pct') + '%');
    });
    seg.addEventListener('mousemove', moveTip);
    seg.addEventListener('mouseleave', hideTip);
  });

  // ── Legend ↔ segment cross-highlight ────────────────────────
  document.querySelectorAll('.leg-item').forEach(function (li) {
    var idx     = li.getAttribute('data-idx');
    var wrapId  = li.closest('[id$="-wrap"]') ? li.closest('[id$="-wrap"]').id.replace('-wrap', '') : null;

    function getSegs() {
      if (!wrapId) return [];
      var wrap = document.getElementById(wrapId);
      return wrap ? Array.from(wrap.querySelectorAll('.donut-seg[data-idx="' + idx + '"]')) : [];
    }

    li.addEventListener('mouseenter', function () {
      getSegs().forEach(function (s) { s.style.filter = 'brightness(1.22)'; s.style.opacity = '1'; });
    });
    li.addEventListener('mouseleave', function () {
      getSegs().forEach(function (s) { s.style.filter = ''; s.style.opacity = ''; });
    });
  });

  // ── Bar animation — triggered by IntersectionObserver ────────
  var barObs = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var el = entry.target;
      var w  = el.getAttribute('data-w');
      if (w) el.style.width = w;
      barObs.unobserve(el);
    });
  }, { threshold: 0.12 });

  document.querySelectorAll('.bar-fill[data-w]').forEach(function (el) { barObs.observe(el); });

  // ── Sample mini-bar animation ────────────────────────────────
  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      document.querySelectorAll('.sample-mini-fill[data-w]').forEach(function (el) {
        el.style.width = el.getAttribute('data-w');
      });
    });
  });

  // ── Interpretation read-more toggle ─────────────────────────
  document.querySelectorAll('.interpretation-toggle').forEach(function (btn) {
    var block  = btn.closest('.interpretation-block');
    var hidden = block ? block.querySelector('.interpretation-hidden') : null;
    if (!hidden) return;

    // Initialise to height:0 so it's collapsed
    hidden.style.height = '0';
    hidden.style.overflow = 'hidden';

    btn.addEventListener('click', function () {
      var expanded = btn.getAttribute('aria-expanded') === 'true';
      var textEl   = btn.querySelector('.toggle-text');
      if (expanded) {
        // Collapse: fix height then animate to 0
        hidden.style.transition = 'none';
        hidden.style.height = hidden.scrollHeight + 'px';
        requestAnimationFrame(function () {
          hidden.style.transition = 'height 0.42s cubic-bezier(0.4, 0, 0.2, 1)';
          hidden.style.height = '0';
        });
        btn.setAttribute('aria-expanded', 'false');
        if (textEl) textEl.textContent = 'Read full interpretation';
      } else {
        // Expand: animate from 0 to content height
        hidden.style.transition = 'height 0.52s cubic-bezier(0.16, 1, 0.3, 1)';
        hidden.style.height = hidden.scrollHeight + 'px';
        btn.setAttribute('aria-expanded', 'true');
        if (textEl) textEl.textContent = 'Collapse interpretation';
        // Remove fixed height after expand so content reflows correctly
        hidden.addEventListener('transitionend', function onEnd() {
          if (btn.getAttribute('aria-expanded') === 'true') {
            hidden.style.height = 'auto';
          }
          hidden.removeEventListener('transitionend', onEnd);
        });
      }
    });
  });

  // ── Collapsible toggle ───────────────────────────────────────
  document.querySelectorAll('.collapsible-toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var section = btn.closest('.section');
      if (section) section.classList.toggle('collapsed');
    });
  });

  // ── TOC active section — IntersectionObserver ────────────────
  var allSections = document.querySelectorAll('section[id]');
  var tocLinks    = document.querySelectorAll('.toc-link');

  var secObs = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var id = entry.target.id;
      tocLinks.forEach(function (lnk) {
        lnk.classList.toggle('active', lnk.getAttribute('href') === '#' + id);
      });
    });
  }, { rootMargin: '-18% 0px -58% 0px', threshold: 0 });

  allSections.forEach(function (s) { secObs.observe(s); });

  // ── Smooth scroll ────────────────────────────────────────────
  tocLinks.forEach(function (lnk) {
    lnk.addEventListener('click', function (e) {
      e.preventDefault();
      var target = document.querySelector(lnk.getAttribute('href'));
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      var mob = document.getElementById('mobile-toc-menu');
      if (mob) mob.classList.remove('open');
    });
  });

  // ── Mobile TOC ───────────────────────────────────────────────
  var mobBtn  = document.getElementById('mob-toc-btn');
  var mobMenu = document.getElementById('mobile-toc-menu');
  if (mobBtn && mobMenu) {
    mobBtn.addEventListener('click', function () { mobMenu.classList.toggle('open'); });
    document.addEventListener('click', function (e) {
      if (mobMenu.classList.contains('open') && !mobMenu.contains(e.target) && e.target !== mobBtn) {
        mobMenu.classList.remove('open');
      }
    });
  }

  // ── Theme toggle ─────────────────────────────────────────────
  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('g25-theme', t); } catch (e) {}
  }

  // Restore persisted preference immediately
  try {
    var saved = localStorage.getItem('g25-theme');
    if (saved === 'light' || saved === 'dark') { applyTheme(saved); }
  } catch (e) {}

  // Wire all toggle buttons (sidebar + mobile nav)
  document.querySelectorAll('.theme-toggle-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var current = document.documentElement.getAttribute('data-theme') || 'dark';
      applyTheme(current === 'dark' ? 'light' : 'dark');
    });
  });

})();
"""
