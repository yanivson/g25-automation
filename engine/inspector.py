"""
engine/inspector.py — enhanced post-clone Vahaduo source code inspection.

Two-stage inspection:

Stage 1 — Static analysis:
  - Parse all HTML files for inline <script> blocks and external <script src> refs
  - Classify scripts as local / inline / remote
  - Extract all DOM element IDs and classes (textarea, input, button, select, div, pre)
  - Scan all script content for relevant keywords
  - Collect matching snippets with file/line context

Stage 2 — Runtime analysis (requires Playwright + running server):
  - Launch the page headlessly
  - Dump document.readyState
  - Dump all live <script src> URLs from the DOM
  - Dump candidate textarea/button/div selectors from the live DOM
  - Dump window keys containing relevant keywords (run, result, distance, model, etc.)

Output: data/vahaduo_engine/.inspection.json (rich structured report)
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

_KEYWORDS = [
    "source", "target", "run", "single", "distance",
    "result", "output", "model", "admixture", "button",
    "textarea", "calculate", "fit", "score",
]

_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _KEYWORDS) + r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ScriptRef(BaseModel):
    kind: str          # "local" | "inline" | "remote"
    src: str           # URL or "(inline)" or file path
    source_file: str   # which HTML file it was found in
    size_chars: int = 0


class KeywordMatch(BaseModel):
    keyword: str
    context_line: str
    source: str        # "local:<path>:N" | "inline:<html>:N" | "remote:<url>"


class DomElement(BaseModel):
    tag: str
    element_id: str | None
    classes: list[str]
    source_file: str
    line: int


class VahaduoInspection(BaseModel):
    report_path: str

    # Stage 1 — static
    html_files: list[str]
    local_js_files: list[str]
    script_refs: list[ScriptRef]
    dom_elements: list[DomElement]
    keyword_matches: list[KeywordMatch]

    # Inventories
    inline_script_snippets: list[str] = Field(default_factory=list)
    remote_script_urls: list[str] = Field(default_factory=list)
    local_script_paths: list[str] = Field(default_factory=list)

    # Stage 2 — runtime (populated if Playwright inspection runs)
    runtime_available: bool = False
    runtime_ready_state: str | None = None
    runtime_script_srcs: list[str] = Field(default_factory=list)
    runtime_window_keys: list[str] = Field(default_factory=list)
    runtime_dom_elements: list[dict] = Field(default_factory=list)

    # Summary
    direct_function_available: bool = False
    logic_location: str = "unknown"   # "local_js" | "inline" | "remote" | "mixed"
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 1 — Static HTML / JS parser
# ---------------------------------------------------------------------------

class _HTMLExtractor(HTMLParser):
    """Extract script refs, inline script content, and relevant DOM elements."""

    TRACKED_TAGS = {"textarea", "input", "button", "select", "div", "pre", "span", "form"}

    def __init__(self, source_file: str) -> None:
        super().__init__()
        self.source_file = source_file
        self.script_refs: list[ScriptRef] = []
        self.dom_elements: list[DomElement] = []
        self._in_script = False
        self._inline_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)

        if tag == "script":
            src = attr_dict.get("src")
            if src:
                if src.startswith("http://") or src.startswith("https://") or src.startswith("//"):
                    kind = "remote"
                elif src.startswith("/") or src.endswith(".js"):
                    kind = "local"
                else:
                    kind = "local"
                self.script_refs.append(ScriptRef(
                    kind=kind,
                    src=src,
                    source_file=self.source_file,
                ))
            else:
                self._in_script = True
                self._inline_buf = []
            return

        if tag.lower() in self.TRACKED_TAGS:
            el_id = attr_dict.get("id")
            classes_raw = attr_dict.get("class", "") or ""
            classes = [c for c in classes_raw.split() if c]
            line, _ = self.getpos()
            self.dom_elements.append(DomElement(
                tag=tag,
                element_id=el_id,
                classes=classes,
                source_file=self.source_file,
                line=line,
            ))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_script:
            self._in_script = False
            content = "".join(self._inline_buf)
            if content.strip():
                self.script_refs.append(ScriptRef(
                    kind="inline",
                    src="(inline)",
                    source_file=self.source_file,
                    size_chars=len(content),
                ))
                # Store content on the ref for keyword scanning later
                self.script_refs[-1].__dict__["_content"] = content
            self._inline_buf = []

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._inline_buf.append(data)


def _scan_text_for_keywords(
    text: str,
    source_label: str,
    matches: list[KeywordMatch],
    max_matches_per_source: int = 50,
) -> None:
    """Scan *text* line by line for keyword matches, appending to *matches*."""
    count = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _KEYWORD_RE.finditer(line):
            matches.append(KeywordMatch(
                keyword=m.group(0).lower(),
                context_line=line.strip()[:300],
                source=f"{source_label}:{lineno}",
            ))
            count += 1
            if count >= max_matches_per_source:
                return


def _static_inspection(engine_path: Path) -> dict:
    """Run the full Stage 1 static analysis. Returns partial report data."""
    html_files: list[str] = []
    local_js_files: list[str] = []
    all_script_refs: list[ScriptRef] = []
    all_dom_elements: list[DomElement] = []
    keyword_matches: list[KeywordMatch] = []
    inline_snippets: list[str] = []
    notes: list[str] = []

    # --- Walk filesystem ---
    for path in sorted(engine_path.rglob("*")):
        if not path.is_file():
            continue
        # Skip hidden dirs and .git
        if any(part.startswith(".") for part in path.parts):
            continue

        rel = str(path.relative_to(engine_path))

        if path.suffix == ".html":
            html_files.append(rel)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            extractor = _HTMLExtractor(source_file=rel)
            try:
                extractor.feed(text)
            except Exception as e:
                notes.append(f"HTML parse error in {rel}: {e}")

            all_script_refs.extend(extractor.script_refs)
            all_dom_elements.extend(extractor.dom_elements)

            # Keyword scan: inline blocks
            for ref in extractor.script_refs:
                if ref.kind == "inline":
                    content = ref.__dict__.get("_content", "")
                    if content:
                        inline_snippets.append(
                            f"=== inline in {rel} ({len(content)} chars) ===\n"
                            + content[:2000]
                        )
                        _scan_text_for_keywords(
                            content,
                            f"inline:{rel}",
                            keyword_matches,
                        )

            # Keyword scan: full HTML text (catches data-* attrs, comments, etc.)
            _scan_text_for_keywords(text, f"html:{rel}", keyword_matches, max_matches_per_source=100)

        elif path.suffix == ".js":
            local_js_files.append(rel)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            _scan_text_for_keywords(text, f"local:{rel}", keyword_matches)

    # Classify refs
    remote_urls = sorted({r.src for r in all_script_refs if r.kind == "remote"})
    local_paths = sorted({r.src for r in all_script_refs if r.kind == "local"})

    # Logic location heuristic
    if local_js_files:
        logic = "local_js"
    elif inline_snippets:
        logic = "inline"
    elif remote_urls:
        logic = "remote"
    else:
        logic = "unknown"

    if not local_js_files and remote_urls:
        notes.append(
            "No local JS files found. App logic appears to be loaded from remote CDN/URLs. "
            "Runtime inspection (Stage 2) is required to observe the live DOM and window state."
        )
    if not local_js_files and not inline_snippets:
        notes.append(
            "WARNING: No local JS and no inline scripts found in static HTML. "
            "The actual admixture tool may be in a different subdirectory or a different GitHub repo. "
            "Check if the correct repo was cloned — the tool at vahaduo.github.io/vahaduo/ "
            "is likely in github.com/vahaduo/vahaduo, not github.com/vahaduo/vahaduo.github.io."
        )

    return {
        "html_files": html_files,
        "local_js_files": local_js_files,
        "script_refs": all_script_refs,
        "dom_elements": all_dom_elements,
        "keyword_matches": keyword_matches,
        "inline_script_snippets": inline_snippets,
        "remote_script_urls": remote_urls,
        "local_script_paths": local_paths,
        "logic_location": logic,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Stage 2 — Runtime Playwright inspection
# ---------------------------------------------------------------------------

_RUNTIME_SCRIPT = """
() => {
    const KEYWORDS = ['run', 'result', 'distance', 'model', 'single', 'admixture',
                      'source', 'target', 'calculate', 'output', 'fit', 'score'];

    // All live script src URLs
    const scriptSrcs = Array.from(document.querySelectorAll('script[src]'))
        .map(s => s.src);

    // Window keys matching keywords
    const winKeys = Object.keys(window).filter(k => {
        const kl = k.toLowerCase();
        return KEYWORDS.some(kw => kl.includes(kw));
    });

    // Candidate DOM elements: textarea, input[type!=hidden], button, select,
    // div/pre/span with result-like IDs or classes
    const candidateSelectors = [
        'textarea',
        'input:not([type="hidden"])',
        'button',
        'select',
    ];
    const elements = [];
    candidateSelectors.forEach(sel => {
        document.querySelectorAll(sel).forEach(el => {
            elements.push({
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                classes: Array.from(el.classList),
                type: el.type || null,
                placeholder: el.placeholder || null,
                textContent: el.textContent ? el.textContent.trim().slice(0, 80) : null,
                name: el.name || null,
            });
        });
    });

    // Also scan divs/pres that have result/distance/output in their id or class
    const RESULT_WORDS = ['result', 'output', 'distance', 'model', 'admix'];
    document.querySelectorAll('div,pre,span,p').forEach(el => {
        const idStr = (el.id || '').toLowerCase();
        const classStr = Array.from(el.classList).join(' ').toLowerCase();
        if (RESULT_WORDS.some(w => idStr.includes(w) || classStr.includes(w))) {
            elements.push({
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                classes: Array.from(el.classList),
                type: null,
                placeholder: null,
                textContent: el.textContent ? el.textContent.trim().slice(0, 80) : null,
                name: null,
            });
        }
    });

    return {
        readyState: document.readyState,
        title: document.title,
        url: window.location.href,
        scriptSrcs,
        winKeys,
        elements,
    };
}
"""


def _runtime_inspection(url: str) -> dict:
    """
    Launch the page with Playwright and extract live DOM/window state.

    Returns a dict with runtime_ fields, or an error note if Playwright fails.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "runtime_available": False,
            "notes_runtime": ["Playwright not installed — skipping runtime inspection."],
        }

    result: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                # Wait for network to mostly settle
                page.goto(url, wait_until="networkidle", timeout=30_000)
                data = page.evaluate(_RUNTIME_SCRIPT)
                result = {
                    "runtime_available": True,
                    "runtime_ready_state": data.get("readyState"),
                    "runtime_title": data.get("title"),
                    "runtime_url": data.get("url"),
                    "runtime_script_srcs": data.get("scriptSrcs", []),
                    "runtime_window_keys": data.get("winKeys", []),
                    "runtime_dom_elements": data.get("elements", []),
                    "notes_runtime": [],
                }
                n_el = len(result["runtime_dom_elements"])
                n_scripts = len(result["runtime_script_srcs"])
                n_keys = len(result["runtime_window_keys"])
                print(
                    f"[inspector] Runtime: readyState={result['runtime_ready_state']}, "
                    f"script_srcs={n_scripts}, window_keys={n_keys}, dom_elements={n_el}"
                )
            finally:
                browser.close()

    except Exception as exc:
        result = {
            "runtime_available": False,
            "notes_runtime": [f"Runtime inspection failed: {exc}"],
        }

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def inspect_vahaduo(
    engine_path: Path,
    server_url: str | None = None,
    run_runtime: bool = True,
) -> VahaduoInspection:
    """
    Full two-stage inspection of the cloned Vahaduo engine.

    Parameters
    ----------
    engine_path:
        Root of the cloned Vahaduo static site.
    server_url:
        Base URL of the running local server (e.g. ``"http://localhost:8080"``).
        If None and run_runtime=True, a temporary LocalVahaduoServer is started.
    run_runtime:
        If True, run Stage 2 Playwright inspection.

    Returns
    -------
    VahaduoInspection
        Full inspection report, also written to engine_path/.inspection.json.
    """
    if not engine_path.exists():
        raise FileNotFoundError(
            f"Engine path does not exist: {engine_path}. "
            "Run 'python scripts/bootstrap.py' first."
        )

    print(f"[inspector] Stage 1: static analysis of {engine_path}")
    static = _static_inspection(engine_path)

    runtime_data: dict = {
        "runtime_available": False,
        "runtime_ready_state": None,
        "runtime_script_srcs": [],
        "runtime_window_keys": [],
        "runtime_dom_elements": [],
    }
    runtime_notes: list[str] = []

    if run_runtime:
        print("[inspector] Stage 2: runtime inspection via Playwright")
        if server_url is None:
            # Start a temporary server
            try:
                from engine.local_server import LocalVahaduoServer
                with LocalVahaduoServer(engine_path) as url:
                    print(f"[inspector] Serving at {url}")
                    rd = _runtime_inspection(url)
            except Exception as exc:
                rd = {
                    "runtime_available": False,
                    "notes_runtime": [f"Could not start local server: {exc}"],
                }
        else:
            rd = _runtime_inspection(server_url)

        runtime_data.update({k: v for k, v in rd.items() if not k.startswith("notes_")})
        runtime_notes = rd.get("notes_runtime", [])
    else:
        runtime_notes = ["Runtime inspection skipped (run_runtime=False)."]

    # Direct function heuristic: a window key that looks like a user-defined callable.
    # Exclude browser built-ins starting with "on" (e.g. ontransitionrun) and
    # common native globals that aren't tool functions.
    _BUILTIN_PREFIXES = ("on", "webkit", "moz", "__", "chrome", "safari")
    direct_feasible = any(
        k for k in runtime_data.get("runtime_window_keys", [])
        if any(kw in k.lower() for kw in ["run", "calc", "model", "fit", "admix"])
        and not any(k.lower().startswith(p) for p in _BUILTIN_PREFIXES)
    )

    all_notes = static["notes"] + runtime_notes
    if not all_notes:
        all_notes.append("Inspection complete. Review this report before implementing the bridge.")

    inspection = VahaduoInspection(
        report_path=str(engine_path / ".inspection.json"),
        html_files=static["html_files"],
        local_js_files=static["local_js_files"],
        script_refs=static["script_refs"],
        dom_elements=static["dom_elements"],
        keyword_matches=static["keyword_matches"],
        inline_script_snippets=static["inline_script_snippets"],
        remote_script_urls=static["remote_script_urls"],
        local_script_paths=static["local_script_paths"],
        runtime_available=runtime_data["runtime_available"],
        runtime_ready_state=runtime_data.get("runtime_ready_state"),
        runtime_script_srcs=runtime_data.get("runtime_script_srcs", []),
        runtime_window_keys=runtime_data.get("runtime_window_keys", []),
        runtime_dom_elements=runtime_data.get("runtime_dom_elements", []),
        direct_function_available=direct_feasible,
        logic_location=static["logic_location"],
        notes=all_notes,
    )

    # Write full report
    report_path = engine_path / ".inspection.json"
    report_path.write_text(
        json.dumps(inspection.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[inspector] Report written to {report_path}")
    _print_summary(inspection)

    return inspection


def _print_summary(i: VahaduoInspection) -> None:
    sep = "-" * 50
    print(f"\n{sep}")
    print("Inspection Summary")
    print(sep)
    print(f"  HTML files:           {len(i.html_files)}")
    print(f"  Local JS files:       {len(i.local_js_files)}")
    print(f"  Remote script URLs:   {len(i.remote_script_urls)}")
    print(f"  Inline script blocks: {len([r for r in i.script_refs if r.kind == 'inline'])}")
    print(f"  DOM elements found:   {len(i.dom_elements)}")
    print(f"  Keyword matches:      {len(i.keyword_matches)}")
    print(f"  Logic location:       {i.logic_location}")
    if i.runtime_available:
        print(f"  Runtime page state:   {i.runtime_ready_state}")
        print(f"  Live script srcs:     {len(i.runtime_script_srcs)}")
        print(f"  Matching window keys: {len(i.runtime_window_keys)}")
        print(f"  Live DOM elements:    {len(i.runtime_dom_elements)}")
    print(f"  Direct fn available:  {i.direct_function_available}")
    print("  Notes:")
    for note in i.notes:
        print(f"    - {note}")
    print(sep)
