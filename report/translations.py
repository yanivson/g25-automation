"""report/translations.py — Centralized translation system for all supported languages.

Rules
-----
- All UI strings must be defined here.
- Narrative interpretation content is NOT stored here (loaded from .txt files).
- No runtime translation. No external APIs.
- English is the canonical source; Hebrew is a complete, independent entry.
- Sample IDs (e.g. Italy_Tuscany_Grosseto_Imperial) are database identifiers, not UI strings.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Country name translations
# ---------------------------------------------------------------------------

COUNTRY_HE: dict[str, str] = {
    "Italy":        "איטליה",
    "Lebanon":      "ישראל",
    "Lithuania":    "ליטא",
    "Greece":       "יוון",
    "Turkey":       "טורקיה",
    "Anatolia":     "אנטוליה",
    "Syria":        "סוריה",
    "Israel":       "ישראל",
    "Poland":       "פולין",
    "Germany":      "גרמניה",
    "Ukraine":      "אוקראינה",
    "Russia":       "רוסיה",
    "France":       "צרפת",
    "Spain":        "ספרד",
    "Serbia":       "סרביה",
    "Croatia":      "קרואטיה",
    "Latvia":       "לטביה",
    "Estonia":      "אסטוניה",
    "Romania":      "רומניה",
    "Hungary":      "הונגריה",
    "Bulgaria":     "בולגריה",
    "Albania":      "אלבניה",
    "Balkans":      "הבלקן",
    "Other European (Balkan/Baltic)": "אירופאי אחר (בלקן/בלטי)",
    "Other European (Baltic/Balkan)": "אירופאי אחר (בלטי/בלקן)",
    "Other European (Baltic)":        "אירופאי אחר (בלטי)",
    "Other European (Balkan)":        "אירופאי אחר (בלקני)",
    "Other European":                 "אירופאי אחר",
    "Other Mediterranean":            "ים-תיכוני אחר",
    "Other Near Eastern":             "מזרח-תיכוני אחר",
}

# ---------------------------------------------------------------------------
# Macro-region translations
# ---------------------------------------------------------------------------

MACRO_HE: dict[str, str] = {
    "Eastern Mediterranean":  "מזרח הים התיכון",
    "Southern Europe":        "דרום אירופה",
    "Northern Europe":        "צפון אירופה",
    "Eastern Europe":         "מזרח אירופה",
    "Northeastern Europe":    "צפון-מזרח אירופה",
    "Central Europe":         "מרכז אירופה",
    "Western Europe":         "מערב אירופה",
    "Anatolia":               "אנטוליה",
    "Levant":                 "לבנט",
    "Baltic":                 "הבלטי",
    "Near East":              "המזרח התיכון",
}

# ---------------------------------------------------------------------------
# Period name translations
# ---------------------------------------------------------------------------

PERIOD_HE: dict[str, str] = {
    "Bronze Age":        "תקופת הברונזה",
    "Iron Age":          "תקופת הברזל",
    "Classical":         "העת העתיקה הקלאסית",
    "Late Antiquity":    "העת העתיקה המאוחרת",
    "Medieval":          "ימי הביניים",
    "Roman":             "התקופה הרומית",
    "Roman Imperial":    "האימפריה הרומית",
    "Byzantine":         "התקופה הביזנטית",
    "Neolithic":         "התקופה הניאוליתית",
    "Chalcolithic":      "תקופת הנחושת",
    "Modern":            "עידן מודרני",
    "Undated":           "לא מתוארך",
    "Mixed":             "מעורב",
}

# ---------------------------------------------------------------------------
# Translation lookup helpers
# ---------------------------------------------------------------------------

def translate_country(name: str, lang: str) -> str:
    if lang != "he":
        return name
    return COUNTRY_HE.get(name, name)


def translate_macro(name: str, lang: str) -> str:
    if lang != "he":
        return name
    return MACRO_HE.get(name, name)


def translate_period(name: str, lang: str) -> str:
    if lang != "he":
        return name
    return PERIOD_HE.get(name, name)


QUALITY_HE: dict[str, str] = {
    "excellent fit": "התאמה מדויקת",
    "good fit":      "התאמה טובה",
    "fair fit":      "התאמה בינונית",
    "poor fit":      "התאמה חלשה",
}


def translate_quality(text: str, lang: str) -> str:
    if lang != "he":
        return text
    return QUALITY_HE.get(text.lower(), text)


# ---------------------------------------------------------------------------
# Full UI label dictionaries
# ---------------------------------------------------------------------------

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Meta
        "report_title":             "Genetic Ancestry Report",
        "ancestry_report":          "Ancestry Report",
        "contents":                 "Contents",
        "generated_from":           "Generated from run",
        "footer_note":              "All ancient reference samples are genetic proxies only.\nResults do not constitute ethnic or genealogical determinations.",

        # TOC labels
        "toc_overview":             "Overview",
        "toc_ancestry":             "Ancestry",
        "toc_interp":               "Ancestry Interp.",
        "toc_samples":              "Samples",
        "toc_ydna":                 "Y-DNA Interp.",
        "toc_technical":            "Technical",

        # Section headers
        "sec_b_eyebrow":            "Model-Level Summary",
        "sec_b_title":              "Ancestry Distribution",
        "sec_b_sub":                "by_country is the primary evidence \u2014 ancient populations as genetic proxies",
        "sec_c_title":              "Ancestry Interpretation",
        "sec_c_sub":                "Bronze Age \u2192 Roman &amp; Byzantine \u2192 Medieval \u2014 ancient populations are genetic proxies only",
        "sec_d_eyebrow":            "Raw Genetic Proxies",
        "sec_d_title":              "Sample-Level Proxies",
        "sec_d_sub":                "Top contributing reference populations \u2014 supporting detail below ancestry distribution",
        "sec_e_title":              "Technical Appendix",
        "sec_e_sub":                "Run metadata and artifact references",
        "sec_f_title":              "Y\u2011DNA Interpretation",
        "sec_f_sub":                "Paternal lineage analysis \u2014 single line only, does not represent full ancestry",

        # Chart labels
        "col_distribution":         "Distribution",
        "col_ranked":               "Ranked Breakdown",
        "col_macro":                "Macro\nRegion",

        # Key signal card
        "key_signal_title":         "Key Genetic Signal",
        "primary_signal":           "Primary signal",
        "secondary_signal":         "Secondary signal",
        "strongest_country":        "Strongest country proxy",
        "closest_period":           "Closest period fit",

        # Period signal card
        "period_signal_title":      "Historical Period Signal",
        "period_signal_note":       "This is the closest single-period approximation. The overall mixed-period model remains the primary result.",

        # Period detail block
        "best_period_fit":          "Best Period Fit",
        "period_col":               "Period",
        "approx_years":             "Approx. Years",
        "distance_col":             "Distance",
        "period_diagnostics":       "Period Diagnostics",
        "period_longer_bar":        "Longer bar = closer genetic fit (lower distance). \u2605 = best-matching period.",
        "no_period_data":           "Period diagnostics were not generated for this run.",

        # Distance badge
        "distance":                 "Distance",

        # Hero
        "closest_fit":              "Closest overall fit",
        "dominant_affinity":        "Dominant affinity",
        "strongest_country_metric": "Strongest country proxy",
        "closest_period_metric":    "Closest historical period",
        "fit_quality":              "Fit quality",

        # Interpretation
        "read_more":                "Read full interpretation",
        "collapse_hint":            "Summary shown \u2014 expand for full historical interpretation",
        "interp_placeholder":       "Historical interpretation has not yet been added.",
        "interp_placeholder_path":  "interpretation/interpretation.txt",

        # Section notes
        "sec_b_note":               "The distribution is centered on Eastern Mediterranean and Southern European populations, with secondary variation reflecting regional admixture.",
        "sec_d_note":               "These samples represent closest-fit ancient and historical proxies and should be interpreted as population approximations rather than direct ancestry.",

        # Sample cards
        "sample_proxy_note":        "Ancient samples serve as genetic proxies \u2014 they are reference populations, not direct ancestors.",
        "sample_minor_note":        "{n} additional sample{s} contribute {pct}% combined (each <1%).",

        # Technical meta
        "meta_run_id":              "Run ID",
        "meta_profile":             "Profile",
        "meta_best_distance":       "Best Distance",
        "meta_fit_quality":         "Fit Quality",
        "meta_best_iter":           "Best Iteration",
        "meta_stop_reason":         "Stop Reason",
        "meta_identity":            "Identity Context",
        "meta_ydna":                "Y-DNA Haplogroup",
    },

    "he": {
        # Meta
        "report_title":             "\u05d3\u05d5\u05d7 \u05de\u05d5\u05e6\u05d0 \u05d2\u05e0\u05d8\u05d9",
        "ancestry_report":          "\u05d3\u05d5\u05d7 \u05de\u05d5\u05e6\u05d0",
        "contents":                 "\u05ea\u05d5\u05db\u05df \u05d4\u05e2\u05e0\u05d9\u05d9\u05e0\u05d9\u05dd",
        "generated_from":           "\u05e0\u05d5\u05e6\u05e8 \u05de\u05e8\u05d9\u05e6\u05d4",
        "footer_note":              "\u05db\u05dc \u05d4\u05d3\u05d2\u05d9\u05de\u05d5\u05ea \u05d4\u05e2\u05ea\u05d9\u05e7\u05d5\u05ea \u05d4\u05df \u05d0\u05d5\u05db\u05dc\u05d5\u05e1\u05d9\u05d5\u05ea \u05d9\u05d9\u05d7\u05d5\u05e1 \u05d1\u05dc\u05d1\u05d3 \u05d5\u05d0\u05d9\u05e0\u05df \u05de\u05e2\u05d9\u05d3\u05d5\u05ea \u05e2\u05dc \u05de\u05d5\u05e6\u05d0 \u05d9\u05e9\u05d9\u05e8.",

        # TOC labels
        "toc_overview":             "\u05e1\u05e7\u05d9\u05e8\u05d4 \u05db\u05dc\u05dc\u05d9\u05ea",
        "toc_ancestry":             "\u05de\u05d5\u05e6\u05d0",
        "toc_interp":               "\u05e4\u05e8\u05e9\u05e0\u05d5\u05ea \u05de\u05d5\u05e6\u05d0",
        "toc_samples":              "\u05d3\u05d2\u05d9\u05de\u05d5\u05ea",
        "toc_ydna":                 "\u05e4\u05e8\u05e9\u05e0\u05ea Y-DNA",
        "toc_technical":            "\u05e0\u05e1\u05e4\u05d7 \u05d8\u05db\u05e0\u05d9",

        # Section headers
        "sec_b_eyebrow":            "\u05e1\u05d9\u05db\u05d5\u05dd \u05de\u05d5\u05d3\u05dc",
        "sec_b_title":              "\u05d4\u05ea\u05e4\u05dc\u05d2\u05d5\u05ea \u05d2\u05e0\u05d8\u05d9\u05ea",
        "sec_b_sub":                "\u05e0\u05ea\u05d5\u05e0\u05d9 \u05de\u05d3\u05d9\u05e0\u05d4 \u05d4\u05dd \u05d4\u05e8\u05d0\u05d9\u05d4 \u05d4\u05e2\u05d9\u05e7\u05e8\u05d9\u05ea \u2014 \u05d0\u05d5\u05db\u05dc\u05d5\u05e1\u05d9\u05d5\u05ea \u05e2\u05ea\u05d9\u05e7\u05d5\u05ea \u05db\u05d0\u05d5\u05db\u05dc\u05d5\u05e1\u05d9\u05d5\u05ea \u05d9\u05d9\u05d7\u05d5\u05e1 \u05d1\u05dc\u05d1\u05d3",
        "sec_c_title":              "\u05e4\u05e8\u05e9\u05e0\u05d5\u05ea \u05de\u05d5\u05e6\u05d0",
        "sec_c_sub":                "\u05d9\u05de\u05d9 \u05d4\u05d1\u05e8\u05d5\u05e0\u05d6\u05d4 \u2192 \u05d4\u05ea\u05e7\u05d5\u05e4\u05d4 \u05d4\u05e8\u05d5\u05de\u05d9\u05ea \u05d5\u05d4\u05d1\u05d9\u05d6\u05e0\u05d8\u05d9\u05ea \u2192 \u05d9\u05de\u05d9 \u05d4\u05d1\u05d9\u05e0\u05d9\u05d9\u05dd \u2014 \u05d0\u05d5\u05db\u05dc\u05d5\u05e1\u05d9\u05d5\u05ea \u05e2\u05ea\u05d9\u05e7\u05d5\u05ea \u05d4\u05df \u05d9\u05d9\u05d7\u05d5\u05e1 \u05d1\u05dc\u05d1\u05d3",
        "sec_d_eyebrow":            "\u05e0\u05ea\u05d5\u05e0\u05d9\u05dd \u05d2\u05e0\u05d8\u05d9\u05d9\u05dd \u05d2\u05d5\u05dc\u05de\u05d9\u05d9\u05dd",
        "sec_d_title":              "\u05d3\u05d2\u05d9\u05de\u05d5\u05ea \u05d4\u05e9\u05d5\u05d5\u05d0\u05d4",
        "sec_d_sub":                "\u05d0\u05d5\u05db\u05dc\u05d5\u05e1\u05d9\u05d5\u05ea \u05d9\u05d9\u05d7\u05d5\u05e1 \u05de\u05d5\u05d1\u05d9\u05dc\u05d5\u05ea \u2014 \u05e4\u05e8\u05d8\u05d9\u05dd \u05ea\u05d5\u05de\u05db\u05d9\u05dd \u05de\u05ea\u05d7\u05ea \u05dc\u05d4\u05ea\u05e4\u05dc\u05d2\u05d5\u05ea \u05d4\u05de\u05d5\u05e6\u05d0",
        "sec_e_title":              "\u05e0\u05e1\u05e4\u05d7 \u05d8\u05db\u05e0\u05d9",
        "sec_e_sub":                "\u05e0\u05ea\u05d5\u05e0\u05d9 \u05e8\u05d9\u05e6\u05d4 \u05d5\u05d4\u05e4\u05e0\u05d9\u05d5\u05ea \u05dc\u05e7\u05d1\u05e6\u05d9\u05dd",
        "sec_f_title":              "Y\u2011DNA \u2014 \u05e4\u05e8\u05e9\u05e0\u05d5\u05ea \u05e7\u05d5 \u05d0\u05d1\u05d9",
        "sec_f_sub":                "\u05e0\u05d9\u05ea\u05d5\u05d7 \u05e9\u05e8\u05e9\u05e8\u05ea \u05d4\u05d0\u05d1 \u2014 \u05e7\u05d5 \u05d9\u05d7\u05d9\u05d3 \u05d1\u05dc\u05d1\u05d3, \u05d0\u05d9\u05e0\u05d5 \u05de\u05d9\u05d9\u05e6\u05d2 \u05d0\u05ea \u05de\u05dc\u05d5\u05d0 \u05d4\u05de\u05d5\u05e6\u05d0",

        # Chart labels
        "col_distribution":         "\u05d4\u05ea\u05e4\u05dc\u05d2\u05d5\u05ea",
        "col_ranked":               "\u05e4\u05d9\u05e8\u05d5\u05d8 \u05dc\u05e4\u05d9 \u05d3\u05d9\u05e8\u05d5\u05d2",
        "col_macro":                "\u05d0\u05d6\u05d5\u05e8\n\u05de\u05d0\u05e7\u05e8\u05d5",

        # Key signal card
        "key_signal_title":         "\u05d0\u05d5\u05ea \u05d2\u05e0\u05d8\u05d9 \u05e2\u05d9\u05e7\u05e8\u05d9",
        "primary_signal":           "\u05d0\u05d5\u05ea \u05e8\u05d0\u05e9\u05d9",
        "secondary_signal":         "\u05d0\u05d5\u05ea \u05de\u05e9\u05e0\u05d9",
        "strongest_country":        "\u05d4\u05ea\u05d0\u05de\u05d4 \u05de\u05d3\u05d9\u05e0\u05ea\u05d9\u05ea \u05de\u05d5\u05d1\u05d9\u05dc\u05ea",
        "closest_period":           "\u05ea\u05e7\u05d5\u05e4\u05d4 \u05e7\u05e8\u05d5\u05d1\u05d4 \u05d1\u05d9\u05d5\u05ea\u05e8",

        # Period signal card
        "period_signal_title":      "\u05d0\u05d5\u05ea \u05ea\u05e7\u05d5\u05e4\u05ea\u05d9",
        "period_signal_note":       "\u05d6\u05d5\u05d4\u05d9 \u05d4\u05e7\u05d9\u05e8\u05d5\u05d1 \u05d4\u05d8\u05d5\u05d1 \u05d1\u05d9\u05d5\u05ea\u05e8 \u05dc\u05ea\u05e7\u05d5\u05e4\u05d4 \u05d9\u05d7\u05d9\u05d3\u05d4. \u05d4\u05de\u05d5\u05d3\u05dc \u05d4\u05db\u05d5\u05dc\u05dc \u05d4\u05d5\u05d0 \u05d4\u05ea\u05d5\u05e6\u05d0\u05d4 \u05d4\u05e2\u05d9\u05e7\u05e8\u05d9\u05ea.",

        # Period detail block
        "best_period_fit":          "\u05ea\u05e7\u05d5\u05e4\u05d4 \u05d1\u05e2\u05dc\u05ea \u05d4\u05d4\u05ea\u05d0\u05de\u05d4 \u05d4\u05d8\u05d5\u05d1\u05d4 \u05d1\u05d9\u05d5\u05ea\u05e8",
        "period_col":               "\u05ea\u05e7\u05d5\u05e4\u05d4",
        "approx_years":             "\u05e9\u05e0\u05d9\u05dd \u05de\u05e9\u05d5\u05e2\u05e8\u05d9\u05dd",
        "distance_col":             "\u05de\u05e8\u05d7\u05e7",
        "period_diagnostics":       "\u05d0\u05d1\u05d7\u05d5\u05df \u05ea\u05e7\u05d5\u05e4\u05ea\u05d9",
        "period_longer_bar":        "\u05e2\u05de\u05d5\u05d3\u05d4 \u05d0\u05e8\u05d5\u05db\u05d4 \u05d9\u05d5\u05ea\u05e8 = \u05d4\u05ea\u05d0\u05de\u05d4 \u05d2\u05e0\u05d8\u05d9\u05ea \u05e7\u05e8\u05d5\u05d1\u05d4 \u05d9\u05d5\u05ea\u05e8. \u2605 = \u05ea\u05e7\u05d5\u05e4\u05d4 \u05d4\u05de\u05ea\u05d0\u05d9\u05de\u05d4 \u05d1\u05d9\u05d5\u05ea\u05e8.",
        "no_period_data":           "\u05d0\u05d1\u05d7\u05d5\u05df \u05ea\u05e7\u05d5\u05e4\u05ea\u05d9 \u05dc\u05d0 \u05d1\u05d5\u05e6\u05e2 \u05e2\u05d1\u05d5\u05e8 \u05e8\u05d9\u05e6\u05d4 \u05d6\u05d5.",

        # Distance badge
        "distance":                 "\u05de\u05e8\u05d7\u05e7",

        # Hero
        "closest_fit":              "\u05d4\u05ea\u05d0\u05de\u05d4 \u05db\u05dc\u05dc\u05d9\u05ea \u05d8\u05d5\u05d1\u05d4 \u05d1\u05d9\u05d5\u05ea\u05e8",
        "dominant_affinity":        "\u05d6\u05d9\u05e7\u05d4 \u05d3\u05d5\u05de\u05d9\u05e0\u05e0\u05d8\u05d9\u05ea",
        "strongest_country_metric": "\u05d4\u05ea\u05d0\u05de\u05d4 \u05de\u05d3\u05d9\u05e0\u05ea\u05d9\u05ea \u05de\u05d5\u05d1\u05d9\u05dc\u05ea",
        "closest_period_metric":    "\u05ea\u05e7\u05d5\u05e4\u05d4 \u05d4\u05d9\u05e1\u05d8\u05d5\u05e8\u05d9\u05ea \u05e7\u05e8\u05d5\u05d1\u05d4",
        "fit_quality":              "\u05d0\u05d9\u05db\u05d5\u05ea \u05d4\u05ea\u05d0\u05de\u05d4",

        # Interpretation
        "read_more":                "\u05e7\u05e8\u05d0 \u05e4\u05e8\u05e9\u05e0\u05d5\u05ea \u05de\u05dc\u05d0\u05d4",
        "collapse_hint":            "\u05de\u05d5\u05e6\u05d2 \u05ea\u05e7\u05e6\u05d9\u05e8 \u2014 \u05dc\u05d7\u05e5 \u05dc\u05d4\u05e8\u05d7\u05d1\u05d4",
        "interp_placeholder":       "\u05e4\u05e8\u05e9\u05e0\u05d5\u05ea \u05d4\u05d9\u05e1\u05d8\u05d5\u05e8\u05d9\u05ea \u05d8\u05e8\u05dd \u05e0\u05d5\u05e1\u05e4\u05d4.",
        "interp_placeholder_path":  "interpretation/interpretation_he.txt",

        # Section notes
        "sec_b_note":               "\u05d4\u05d4\u05ea\u05e4\u05dc\u05d2\u05d5\u05ea \u05de\u05e8\u05d5\u05db\u05d6\u05ea \u05e1\u05d1\u05d9\u05d1 \u05d0\u05d5\u05db\u05dc\u05d5\u05e1\u05d9\u05d5\u05ea \u05de\u05d4\u05de\u05d6\u05e8\u05d7 \u05d4\u05ea\u05d9\u05db\u05d5\u05e0\u05d9 \u05d5\u05d3\u05e8\u05d5\u05dd \u05d0\u05d9\u05e8\u05d5\u05e4\u05d4, \u05e2\u05dd \u05d5\u05e8\u05d9\u05d0\u05e6\u05d9\u05d4 \u05de\u05e9\u05e0\u05d9\u05ea \u05d4\u05de\u05e9\u05e7\u05e4\u05ea \u05e2\u05e8\u05d1\u05d5\u05d1 \u05d0\u05d6\u05d5\u05e8\u05d9.",
        "sec_d_note":               "\u05d3\u05d2\u05d9\u05de\u05d5\u05ea \u05d0\u05dc\u05d5 \u05de\u05d9\u05d9\u05e6\u05d2\u05d5\u05ea \u05d0\u05d5\u05db\u05dc\u05d5\u05e1\u05d9\u05d5\u05ea \u05e7\u05d9\u05e8\u05d5\u05d1 \u05d5\u05d9\u05e9 \u05dc\u05e4\u05e8\u05e9 \u05d0\u05d5\u05ea\u05df \u05db\u05e7\u05d9\u05e8\u05d5\u05d1 \u05d2\u05e0\u05d8\u05d9 \u05d5\u05dc\u05d0 \u05db\u05d9\u05d9\u05d7\u05d5\u05e1 \u05d2\u05e0\u05d0\u05dc\u05d5\u05d2\u05d9 \u05d9\u05e9\u05d9\u05e8.",

        # Sample cards
        "sample_proxy_note":        "\u05d3\u05d2\u05d9\u05de\u05d5\u05ea \u05e2\u05ea\u05d9\u05e7\u05d5\u05ea \u05de\u05e9\u05de\u05e9\u05d5\u05ea \u05db\u05d0\u05d5\u05db\u05dc\u05d5\u05e1\u05d9\u05d5\u05ea \u05d9\u05d9\u05d7\u05d5\u05e1 \u05d1\u05dc\u05d1\u05d3 \u2014 \u05d0\u05d9\u05e0\u05df \u05d0\u05d1\u05d5\u05ea \u05d9\u05e9\u05d9\u05e8\u05d9\u05dd.",
        "sample_minor_note":        "{n} \u05d3\u05d2\u05d9\u05de\u05d5\u05ea \u05e0\u05d5\u05e1\u05e4\u05d5\u05ea \u05ea\u05d5\u05e8\u05de\u05d5\u05ea {pct}% \u05d1\u05e1\u05da \u05d4\u05db\u05dc (\u05db\u05dc \u05d0\u05d7\u05ea \u05e4\u05d7\u05d5\u05ea \u05de-1%).",

        # Technical meta
        "meta_run_id":              "\u05de\u05d6\u05d4\u05d4 \u05e8\u05d9\u05e6\u05d4",
        "meta_profile":             "\u05e4\u05e8\u05d5\u05e4\u05d9\u05dc",
        "meta_best_distance":       "\u05de\u05e8\u05d7\u05e7 \u05de\u05d9\u05d8\u05d1\u05d9",
        "meta_fit_quality":         "\u05d0\u05d9\u05db\u05d5\u05ea \u05d4\u05ea\u05d0\u05de\u05d4",
        "meta_best_iter":           "\u05d0\u05d9\u05d8\u05e8\u05e6\u05d9\u05d4 \u05de\u05d9\u05d8\u05d1\u05d9\u05ea",
        "meta_stop_reason":         "\u05e1\u05d9\u05d1\u05ea \u05e2\u05e6\u05d9\u05e8\u05d4",
        "meta_identity":            "\u05d4\u05e7\u05e9\u05e8 \u05d6\u05d4\u05d5\u05ea\u05d9",
        "meta_ydna":                "\u05d4\u05e4\u05dc\u05d5\u05d2\u05e8\u05d5\u05e4 Y-DNA",
    },
}


def get_t(lang: str) -> dict[str, str]:
    """Return translation dict for the given language, falling back to English."""
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"])


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def validate_hebrew_ui(html: str) -> list[str]:
    """
    Check that Hebrew report section headers contain no raw English UI text.

    Checks only the section body text visible to users (section titles, eyebrows,
    section-sub labels, notes, badges).  Does NOT check:
    - CSS / JS embedded blocks
    - Sample IDs (genetic database identifiers, always Latin)
    - Haplogroup names (scientific notation)
    - Run IDs (numeric/underscore identifiers)
    - HTML attributes and tag names
    - Numeric values

    Returns a list of detected leaks (empty = clean).
    """
    import re

    # Extract only visible section-level text (between section tags, strip all HTML)
    sections_html = re.findall(
        r'<section[^>]*>(.*?)</section>',
        html, re.DOTALL
    )

    leaks: list[str] = []
    # Allowed English tokens in a Hebrew report
    ALLOWED = {
        # Scientific / genetic identifiers — always Latin
        "DNA", "Y-DNA", "SNP", "mtDNA",
        # Haplogroup prefixes
        "I-M223", "I-Y11261", "I-Y38863", "I-Y", "I-M",
        # HTML structural words (won't appear after tag stripping but safety)
        "div", "span", "class", "href",
        # Numerics-adjacent
        "km", "bp",
        # Personal / display names — can't be translated
        "Yaniv", "Yigal", "Sasson",
        # Distance quality strings now translated, but keep as safety net
        "Excellent", "excellent", "Good", "good", "Fair", "fair", "Poor", "poor",
        # Stop-reason pipeline tokens — not UI strings
        "reached", "converged", "iteration", "iterations", "threshold",
        # Jewish/Ashkenazi — appear in executive summary prose fragments
        "Ashkenazi", "Jewish",
    }

    for sec_html in sections_html:
        # Remove style/script blocks
        sec_html = re.sub(r'<style[^>]*>.*?</style>', '', sec_html, flags=re.DOTALL)
        sec_html = re.sub(r'<script[^>]*>.*?</script>', '', sec_html, flags=re.DOTALL)
        # Remove HTML tags + attributes
        text = re.sub(r'<[^>]+>', ' ', sec_html)
        # Remove HTML entities
        text = re.sub(r'&[a-z]+;', ' ', text)
        # Remove run_id patterns (underscore-separated timestamps)
        text = re.sub(r'\d{8}_\d{6}_\d+', ' ', text)
        # Remove sample IDs (contain underscores) — genetic database identifiers
        text = re.sub(r'\b\w+_\w+\b', ' ', text)
        # Remove haplogroup notation
        text = re.sub(r'[A-Z]-[A-Z0-9]+', ' ', text)
        # Remove pure numbers / decimals
        text = re.sub(r'\b[\d.]+\b', ' ', text)

        # Find remaining English words ≥ 4 chars
        words = re.findall(r'[A-Za-z]{4,}', text)
        for w in words:
            if w not in ALLOWED and w.upper() not in ALLOWED:
                leaks.append(w)

    return list(dict.fromkeys(leaks))  # deduplicated, order-preserving
