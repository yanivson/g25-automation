"""
report/sample_enrichment.py — Historical metadata enrichment for G25 sample names.

UI-layer only. No effect on ancestry calculations, aggregations, or interpretations.
All output is for display purposes only.

Enrichment is inferred deterministically from the sample name using:
  1. Token-based period detection (ordered rules, first match wins)
  2. Country-to-group mapping
  3. (country_group, period_group) lookups for culture and description
  4. Locality extraction from residual tokens
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------

_STRIP_GENOME = re.compile(r"\.(SG|DG|WG|UDG|SDG)$", re.IGNORECASE)


def _tokenize(name: str) -> list[str]:
    """Split name by '_', strip genome suffixes from the last token."""
    parts = name.split("_")
    if parts:
        parts[-1] = _STRIP_GENOME.sub("", parts[-1])
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# Period detection rules
# Ordered: more specific rules come first.
# Each entry: (match_keywords_lc, period_label, date_range, period_group)
# A rule matches if any keyword appears as an exact token in the lowercased tokens.
# Keywords >= 5 chars also match as substrings (for compound tokens like "earlybyzantine").
# ---------------------------------------------------------------------------

_PERIOD_RULES: list[tuple[list[str], str, str, str]] = [
    (["mesolithic"],                              "Mesolithic",             "c. 10000–7000 BCE", "prehistoric"),
    (["earlyneolithic"],                          "Early Neolithic",        "c. 7000–5500 BCE",  "neolithic"),
    (["lateneolithic"],                           "Late Neolithic",         "c. 4500–3500 BCE",  "neolithic"),
    (["finalneolithic"],                          "Final Neolithic",        "c. 3500–2800 BCE",  "neolithic"),
    (["neolithic"],                               "Neolithic",              "c. 7000–3500 BCE",  "neolithic"),
    (["chalcolithic", "chl", "copper", "eneolithic"], "Chalcolithic",       "c. 4500–3300 BCE",  "chalcolithic"),
    (["eba", "earlyba"],                          "Early Bronze Age",       "c. 3300–2000 BCE",  "bronze_age"),
    (["mlba"],                                    "Middle–Late Bronze Age", "c. 2000–1200 BCE",  "bronze_age"),
    (["lba"],                                     "Late Bronze Age",        "c. 1500–1200 BCE",  "bronze_age"),
    (["mba"],                                     "Middle Bronze Age",      "c. 2000–1500 BCE",  "bronze_age"),
    (["ba"],                                      "Bronze Age",             "c. 3300–1200 BCE",  "bronze_age"),
    (["eia"],                                     "Early Iron Age",         "c. 800–500 BCE",    "iron_age"),
    (["mia"],                                     "Middle Iron Age",        "c. 500–200 BCE",    "iron_age"),
    (["lia"],                                     "Late Iron Age",          "c. 200 BCE–100 CE", "iron_age"),
    (["ia"],                                      "Iron Age",               "c. 800–100 BCE",    "iron_age"),
    (["hellenistic"],                             "Hellenistic",            "c. 325–30 BCE",     "classical"),
    (["classical", "archaic"],                    "Classical",              "c. 500–200 BCE",    "classical"),
    (["earlybyzantine", "earlybyzan"],            "Early Byzantine",        "c. 330–500 CE",     "late_antique"),
    (["byzantine", "byzan"],                      "Byzantine",              "c. 330–700 CE",     "late_antique"),
    (["lateantiquity", "lateant"],                "Late Antiquity",         "c. 300–700 CE",     "late_antique"),
    (["earlymedieval", "emedieval", "earlymed"],  "Early Medieval",         "c. 500–900 CE",     "medieval"),
    (["viking"],                                  "Viking Age",             "c. 800–1050 CE",    "medieval"),
    (["anglosaxon"],                              "Anglo-Saxon",            "c. 450–1066 CE",    "medieval"),
    (["saxon"],                                   "Saxon",                  "c. 400–900 CE",     "medieval"),
    (["earlyroman"],                              "Early Roman",            "c. 100 BCE–100 CE", "roman"),
    (["lateroman"],                               "Late Roman",             "c. 200–400 CE",     "roman"),
    (["roman"],                                   "Roman Period",           "c. 100 BCE–400 CE", "roman"),
    (["ottoman"],                                 "Ottoman Period",         "c. 1300–1700 CE",   "early_modern"),
    (["medieval"],                                "Medieval",               "c. 900–1400 CE",    "medieval"),
    (["earlymodern"],                             "Early Modern",           "c. 1500–1800 CE",   "early_modern"),
    (["iron"],                                    "Iron Age",               "c. 800–100 BCE",    "iron_age"),
    (["bronze"],                                  "Bronze Age",             "c. 3300–1200 BCE",  "bronze_age"),
]

# All known period-related tokens (lowercase) — used to filter non-locality tokens
_PERIOD_TOKEN_SET: frozenset[str] = frozenset(
    kw for rule in _PERIOD_RULES for kw in rule[0]
)

# Non-locality labels: genetic variants, culture abbreviations, directional qualifiers
_NON_LOCALITY: frozenset[str] = frozenset({
    "higheef", "loweef", "steppe", "farmer", "hunter", "gatherer",
    "whg", "ehg", "anf", "ana", "cwc", "bbc", "lbk", "tten",
    "celt", "celtic", "gaelic", "germanic", "nordic", "slavic",
    "frankish", "gaulish", "roman", "norse",
    "south", "north", "east", "west", "central", "upper", "lower",
    "early", "late", "middle", "final",
    "high", "low", "mixed", "modern", "ancient", "period",
})


def _detect_period(tokens_lc: list[str]) -> tuple[str, str, str]:
    """Return (period_label, date_range, period_group). Empty strings if not found."""
    token_set = set(tokens_lc)
    for keywords, label, date_range, group in _PERIOD_RULES:
        for kw in keywords:
            if len(kw) >= 5:
                # Substring match for compound tokens
                if any(kw in t for t in token_set):
                    return label, date_range, group
            else:
                # Exact token match only for short codes
                if kw in token_set:
                    return label, date_range, group
    return "", "", "unknown"


def _extract_locality(tokens: list[str]) -> str:
    """Extract sub-locality tokens: non-country, non-period, non-variant, capitalized."""
    if len(tokens) <= 1:
        return ""
    known = _PERIOD_TOKEN_SET | _NON_LOCALITY
    parts: list[str] = []
    for tok in tokens[1:]:  # Skip first (country) token
        tok_lc = tok.lower()
        if tok_lc in known:
            continue
        # Genetic variant labels like "highEEF", "lowEEF"
        if re.match(r"^(high|low|mid|rich)[a-z]", tok_lc):
            continue
        # All-uppercase abbreviations ≤ 4 chars are codes, not place names
        if tok.isupper() and len(tok) <= 4:
            continue
        # Keep tokens that start with uppercase (likely a proper noun / place name)
        if tok and tok[0].isupper():
            parts.append(tok)
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Country → group mapping
# ---------------------------------------------------------------------------

_COUNTRY_TO_GROUP: dict[str, str] = {
    "Scotland": "british_isles", "England": "british_isles",
    "Ireland": "british_isles", "Wales": "british_isles",
    "Britain": "british_isles", "IsleOfMan": "british_isles",
    "ChannelIslands": "british_isles",
    "France": "france", "Belgium": "france", "Luxembourg": "france",
    "Germany": "germanic", "Netherlands": "germanic",
    "Austria": "germanic", "Switzerland": "germanic",
    "Denmark": "scandinavia", "Sweden": "scandinavia",
    "Norway": "scandinavia", "Iceland": "scandinavia",
    "Faroes": "scandinavia", "Scandinavia": "scandinavia",
    "Spain": "iberia", "Portugal": "iberia",
    "Ibiza": "iberia", "CanaryIslands": "iberia", "Gibraltar": "iberia",
    "Italy": "italy",
    "Greece": "balkans", "Croatia": "balkans", "Serbia": "balkans",
    "Bulgaria": "balkans", "Romania": "balkans", "Albania": "balkans",
    "Bosnia": "balkans", "BosniaHerzegovina": "balkans",
    "Macedonia": "balkans", "Slovenia": "balkans", "Montenegro": "balkans",
    "Czech": "central_europe", "Czechia": "central_europe",
    "Slovakia": "central_europe", "Poland": "central_europe",
    "Hungary": "central_europe",
    "Ukraine": "eastern_europe", "Russia": "eastern_europe",
    "Belarus": "eastern_europe", "Moldova": "eastern_europe",
    "Crimea": "eastern_europe",
    "Latvia": "baltic", "Lithuania": "baltic",
    "Estonia": "baltic", "Finland": "baltic",
    "Turkey": "anatolia", "Cyprus": "anatolia",
    "Israel": "levant", "Palestine": "levant",
    "Jordan": "levant", "Lebanon": "levant", "Syria": "levant",
    "Iraq": "mesopotamia",
    "Iran": "iran",
    "Armenia": "caucasus", "Georgia": "caucasus", "Azerbaijan": "caucasus",
    "Egypt": "north_africa", "Morocco": "north_africa",
    "Tunisia": "north_africa", "Algeria": "north_africa",
    "Libya": "north_africa", "Sudan": "north_africa",
    "Saudi": "arabian", "Yemen": "arabian",
    "Kazakhstan": "central_asia", "Kazakhstann": "central_asia",
    "Kazakstan": "central_asia", "Uzbekistan": "central_asia",
    "Turkmenistan": "central_asia", "Kyrgyzstan": "central_asia",
    "Tajikistan": "central_asia", "Mongolia": "central_asia",
    "India": "south_asia", "Pakistan": "south_asia", "Nepal": "south_asia",
}

# Friendly display area names per country prefix
_COUNTRY_AREA: dict[str, str] = {
    "Scotland": "Scotland (UK)", "England": "England (UK)",
    "Ireland": "Ireland", "Wales": "Wales (UK)", "Britain": "Britain (UK)",
    "France": "France", "Belgium": "Belgium",
    "Germany": "Germany", "Netherlands": "Netherlands",
    "Austria": "Austria", "Switzerland": "Switzerland",
    "Denmark": "Denmark", "Sweden": "Sweden", "Norway": "Norway",
    "Iceland": "Iceland", "Faroes": "Faroe Islands",
    "Scandinavia": "Scandinavia",
    "Spain": "Spain", "Portugal": "Portugal", "Italy": "Italy",
    "Greece": "Greece", "Croatia": "Croatia", "Serbia": "Serbia",
    "Bulgaria": "Bulgaria", "Romania": "Romania", "Albania": "Albania",
    "Bosnia": "Bosnia", "BosniaHerzegovina": "Bosnia & Herzegovina",
    "Macedonia": "North Macedonia", "Slovenia": "Slovenia",
    "Montenegro": "Montenegro",
    "Czech": "Czech Republic", "Czechia": "Czech Republic",
    "Slovakia": "Slovakia", "Poland": "Poland", "Hungary": "Hungary",
    "Ukraine": "Ukraine", "Russia": "Russia",
    "Latvia": "Latvia", "Lithuania": "Lithuania",
    "Estonia": "Estonia", "Finland": "Finland",
    "Turkey": "Anatolia / Turkey", "Cyprus": "Cyprus",
    "Israel": "Southern Levant (Israel)",
    "Palestine": "Southern Levant (Palestine)",
    "Jordan": "Southern Levant (Jordan)",
    "Lebanon": "Northern Levant (Lebanon)",
    "Syria": "Northern Levant (Syria)",
    "Iraq": "Mesopotamia (Iraq)",
    "Iran": "Iran",
    "Armenia": "Armenia (South Caucasus)",
    "Georgia": "Georgia (South Caucasus)",
    "Azerbaijan": "Azerbaijan (South Caucasus)",
    "Egypt": "Egypt / Nile Valley",
    "Morocco": "Morocco", "Tunisia": "Tunisia",
    "Algeria": "Algeria", "Libya": "Libya", "Sudan": "Sudan / Nubia",
    "Saudi": "Arabian Peninsula", "Yemen": "Yemen (Arabian Peninsula)",
    "Kazakhstan": "Kazakhstan (Central Asia)",
}

# ---------------------------------------------------------------------------
# Culture lookup: (country_group, period_group) -> culture label
# ---------------------------------------------------------------------------

_CULTURE_MAP: dict[tuple[str, str], str] = {
    ("british_isles", "prehistoric"):  "Mesolithic Hunter-Gatherer",
    ("british_isles", "neolithic"):    "Neolithic Farmer",
    ("british_isles", "chalcolithic"): "Chalcolithic / Bell Beaker",
    ("british_isles", "bronze_age"):   "Bronze Age British",
    ("british_isles", "iron_age"):     "Brythonic Celtic",
    ("british_isles", "roman"):        "Romano-British",
    ("british_isles", "late_antique"): "Sub-Roman / Early Insular",
    ("british_isles", "medieval"):     "Early Medieval British",

    ("scandinavia", "prehistoric"):    "Mesolithic Hunter-Gatherer",
    ("scandinavia", "neolithic"):      "Scandinavian Neolithic (TRB / Pitted Ware)",
    ("scandinavia", "chalcolithic"):   "Battle Axe / Corded Ware",
    ("scandinavia", "bronze_age"):     "Nordic Bronze Age",
    ("scandinavia", "iron_age"):       "Germanic Iron Age",
    ("scandinavia", "roman"):          "Germanic / Roman Iron Age",
    ("scandinavia", "medieval"):       "Norse / Viking",

    ("france", "prehistoric"):         "Mesolithic Hunter-Gatherer",
    ("france", "neolithic"):           "Early European Farmer (LBK)",
    ("france", "chalcolithic"):        "Chalcolithic / Bell Beaker",
    ("france", "bronze_age"):          "Bronze Age (Gaulish precursor)",
    ("france", "iron_age"):            "Gaulish Celtic",
    ("france", "roman"):               "Gallo-Roman",
    ("france", "late_antique"):        "Late Antique / Early Frankish",
    ("france", "medieval"):            "Frankish / Medieval French",

    ("germanic", "prehistoric"):       "Mesolithic Hunter-Gatherer",
    ("germanic", "neolithic"):         "Early European Farmer (LBK)",
    ("germanic", "chalcolithic"):      "Corded Ware / Bell Beaker",
    ("germanic", "bronze_age"):        "Bronze Age Central European",
    ("germanic", "iron_age"):          "Early Germanic",
    ("germanic", "roman"):             "Germanic / Roman Period",
    ("germanic", "late_antique"):      "Late Roman / Migration Period",
    ("germanic", "medieval"):          "Continental Germanic / Frankish",

    ("central_europe", "prehistoric"): "Mesolithic Hunter-Gatherer",
    ("central_europe", "neolithic"):   "Early European Farmer (LBK/AVK)",
    ("central_europe", "chalcolithic"):"Chalcolithic European",
    ("central_europe", "bronze_age"):  "Central European Bronze Age",
    ("central_europe", "iron_age"):    "Celtic / La Tène",
    ("central_europe", "roman"):       "Romanized Provincial",
    ("central_europe", "medieval"):    "Medieval Central European",

    ("eastern_europe", "prehistoric"): "Eastern European Hunter-Gatherer (EHG)",
    ("eastern_europe", "neolithic"):   "Eastern European Neolithic",
    ("eastern_europe", "chalcolithic"):"Chalcolithic / Steppe-related",
    ("eastern_europe", "bronze_age"):  "Steppe Bronze Age (Yamnaya-related)",
    ("eastern_europe", "iron_age"):    "Scythian / Early Slavic",
    ("eastern_europe", "medieval"):    "Medieval Slavic",

    ("baltic", "prehistoric"):         "Baltic Hunter-Gatherer",
    ("baltic", "neolithic"):           "Neolithic Baltic / Comb Ceramic",
    ("baltic", "bronze_age"):          "Bronze Age Baltic",
    ("baltic", "iron_age"):            "Baltic Iron Age",
    ("baltic", "medieval"):            "Medieval Baltic / Finnish",

    ("iberia", "prehistoric"):         "Iberian Mesolithic Hunter-Gatherer",
    ("iberia", "neolithic"):           "Iberian Neolithic Farmer",
    ("iberia", "chalcolithic"):        "Chalcolithic Iberian",
    ("iberia", "bronze_age"):          "Iberian Bronze Age",
    ("iberia", "iron_age"):            "Iberian Celtic / Celtiberian",
    ("iberia", "roman"):               "Hispano-Roman",
    ("iberia", "medieval"):            "Medieval Iberian",

    ("italy", "prehistoric"):          "Italian Mesolithic Hunter-Gatherer",
    ("italy", "neolithic"):            "Italian Neolithic Farmer",
    ("italy", "chalcolithic"):         "Chalcolithic Italian",
    ("italy", "bronze_age"):           "Italic Bronze Age",
    ("italy", "iron_age"):             "Italic / Pre-Roman",
    ("italy", "classical"):            "Hellenistic Italian",
    ("italy", "roman"):                "Roman Imperial",
    ("italy", "late_antique"):         "Late Roman / Byzantine Italian",
    ("italy", "medieval"):             "Medieval Italian / Lombard",

    ("balkans", "prehistoric"):        "Balkan Hunter-Gatherer",
    ("balkans", "neolithic"):          "Early European Farmer (Balkan Neolithic)",
    ("balkans", "chalcolithic"):       "Chalcolithic Balkan",
    ("balkans", "bronze_age"):         "Bronze Age Balkan",
    ("balkans", "iron_age"):           "Thracian / Illyrian Iron Age",
    ("balkans", "classical"):          "Ancient Greek / Hellenistic",
    ("balkans", "roman"):              "Greco-Roman / Romanized Balkan",
    ("balkans", "late_antique"):       "Late Antique / Early Byzantine",
    ("balkans", "medieval"):           "Byzantine / Medieval Balkan",

    ("anatolia", "prehistoric"):       "Anatolian Hunter-Gatherer",
    ("anatolia", "neolithic"):         "Anatolian Neolithic Farmer",
    ("anatolia", "chalcolithic"):      "Chalcolithic Anatolian",
    ("anatolia", "bronze_age"):        "Anatolian / Hittite Bronze Age",
    ("anatolia", "iron_age"):          "Phrygian / Iron Age Anatolian",
    ("anatolia", "classical"):         "Hellenistic Anatolian",
    ("anatolia", "roman"):             "Roman Anatolian",
    ("anatolia", "late_antique"):      "Late Antique / Byzantine Anatolian",
    ("anatolia", "medieval"):          "Byzantine / Seljuk Anatolian",

    ("levant", "prehistoric"):         "Natufian / Epipaleolithic Levantine",
    ("levant", "neolithic"):           "Pre-Pottery Neolithic Levantine",
    ("levant", "chalcolithic"):        "Chalcolithic Levantine",
    ("levant", "bronze_age"):          "Canaanite / Bronze Age Levantine",
    ("levant", "iron_age"):            "Iron Age Levantine",
    ("levant", "classical"):           "Hellenistic Levantine",
    ("levant", "roman"):               "Roman-era Levantine",
    ("levant", "late_antique"):        "Late Antique / Byzantine Levantine",
    ("levant", "medieval"):            "Medieval Levantine",

    ("mesopotamia", "neolithic"):      "Early Mesopotamian Farmer",
    ("mesopotamia", "chalcolithic"):   "Chalcolithic Mesopotamian",
    ("mesopotamia", "bronze_age"):     "Akkadian / Bronze Age Mesopotamian",
    ("mesopotamia", "iron_age"):       "Assyrian / Iron Age Mesopotamian",
    ("mesopotamia", "roman"):          "Parthian-era Mesopotamian",
    ("mesopotamia", "medieval"):       "Medieval Islamic Mesopotamian",

    ("iran", "prehistoric"):           "Zagros Hunter-Gatherer",
    ("iran", "neolithic"):             "Zagros Neolithic Farmer",
    ("iran", "chalcolithic"):          "Chalcolithic Iranian",
    ("iran", "bronze_age"):            "Bronze Age Iranian",
    ("iran", "iron_age"):              "Median / Achaemenid Iranian",
    ("iran", "classical"):             "Achaemenid / Hellenistic Iranian",
    ("iran", "roman"):                 "Parthian / Sassanid Iranian",
    ("iran", "medieval"):              "Islamic Medieval Iranian",

    ("caucasus", "prehistoric"):       "Caucasian Hunter-Gatherer (CHG)",
    ("caucasus", "neolithic"):         "Caucasian Neolithic",
    ("caucasus", "chalcolithic"):      "Chalcolithic Caucasian",
    ("caucasus", "bronze_age"):        "Kura-Araxes / Bronze Age Caucasian",
    ("caucasus", "iron_age"):          "Urartian / Iron Age Caucasian",
    ("caucasus", "classical"):         "Classical Caucasian",
    ("caucasus", "roman"):             "Roman-era Caucasian",
    ("caucasus", "medieval"):          "Medieval Caucasian",

    ("north_africa", "prehistoric"):   "North African Mesolithic Hunter-Gatherer",
    ("north_africa", "neolithic"):     "North African Neolithic",
    ("north_africa", "bronze_age"):    "Bronze Age North African",
    ("north_africa", "iron_age"):      "Phoenician / Berber Iron Age",
    ("north_africa", "roman"):         "Roman North African",
    ("north_africa", "medieval"):      "Medieval North African / Islamic",

    ("central_asia", "bronze_age"):    "Steppe Bronze Age (Andronovo / BMAC)",
    ("central_asia", "iron_age"):      "Scythian / Saka Iron Age",
    ("central_asia", "medieval"):      "Medieval Turkic / Mongol",
}

# ---------------------------------------------------------------------------
# Description lookup: (country_group, period_group) -> 2-3 line description
# ---------------------------------------------------------------------------

_DESCRIPTION_MAP: dict[tuple[str, str], str] = {
    ("british_isles", "prehistoric"):
        "This sample represents Mesolithic hunter-gatherers of Britain before the arrival of farming. "
        "Associated with mobile foraging communities relying on coastal and inland resources.",

    ("british_isles", "neolithic"):
        "This sample represents the earliest farming communities of Britain, arriving from continental Europe. "
        "Associated with monument-building cultures including long barrows and causewayed enclosures.",

    ("british_isles", "chalcolithic"):
        "This sample represents Chalcolithic or Bell Beaker-period populations of Britain. "
        "Associated with the spread of early metalworking and a major genetic turnover of the population.",

    ("british_isles", "bronze_age"):
        "This sample represents Bronze Age populations of Britain. "
        "Typical of agrarian and pastoral communities with emerging social hierarchy and long-distance trade networks.",

    ("british_isles", "iron_age"):
        "This sample represents Iron Age Celtic populations of Britain. "
        "Associated with Brythonic-speaking tribal societies, hillfort construction, and La Tène cultural traditions.",

    ("british_isles", "roman"):
        "This sample represents Romano-British populations during the period of Roman occupation. "
        "Typical of communities integrating Roman urban culture with indigenous British traditions.",

    ("british_isles", "late_antique"):
        "This sample represents sub-Roman or early Insular populations of Britain. "
        "Associated with the post-Roman transition period and the emergence of early medieval kingdoms.",

    ("british_isles", "medieval"):
        "This sample represents early medieval populations of the British Isles. "
        "Typical of communities shaped by successive migrations of Anglo-Saxon, Norse, and Gaelic groups.",

    ("scandinavia", "prehistoric"):
        "This sample represents Mesolithic hunter-gatherers from Scandinavia. "
        "Associated with coastal and inland foraging communities adapted to post-glacial northern environments.",

    ("scandinavia", "neolithic"):
        "This sample represents Neolithic populations of Scandinavia, including Funnel Beaker and related cultures. "
        "Typical of early farming communities alongside persistent hunter-gatherer groups.",

    ("scandinavia", "bronze_age"):
        "This sample represents Nordic Bronze Age populations. "
        "Associated with a distinctive culture known for metalwork, ship burials, and long-distance amber trade.",

    ("scandinavia", "iron_age"):
        "This sample represents Iron Age Germanic populations of Scandinavia. "
        "Precursor to the historically documented Norse societies of the Viking Age.",

    ("scandinavia", "roman"):
        "This sample represents Roman Iron Age populations of Scandinavia. "
        "Associated with Germanic tribal societies in contact with the Roman frontier.",

    ("scandinavia", "medieval"):
        "This sample represents Norse or Viking Age populations of Scandinavia. "
        "Seafaring societies active in raiding, trade, and settlement across Europe and the North Atlantic.",

    ("france", "neolithic"):
        "This sample represents early Neolithic farming populations in what is now France. "
        "Associated with the Linearbandkeramik (LBK) expansion from southeastern Europe.",

    ("france", "chalcolithic"):
        "This sample represents Chalcolithic or Bell Beaker-period populations of France. "
        "Typical of the transition to early metalworking with evidence of increased mobility and trade.",

    ("france", "bronze_age"):
        "This sample represents Bronze Age populations from France. "
        "Typical of communities ancestral to historically documented Gaulish cultures.",

    ("france", "iron_age"):
        "This sample represents Iron Age Gaulish Celtic populations of ancient France. "
        "Typical of Celtic-speaking tribal societies engaged in agriculture, trade, and warfare.",

    ("france", "roman"):
        "This sample represents Gallo-Roman populations of ancient France. "
        "Typical of communities blending indigenous Gaulish culture with Roman urban traditions.",

    ("france", "late_antique"):
        "This sample represents Late Antique populations of France during the Roman-to-Frankish transition. "
        "Associated with the emergence of early medieval Christian communities.",

    ("france", "medieval"):
        "This sample represents Frankish and medieval French populations. "
        "Typical of agrarian communities under Carolingian and later French feudal structures.",

    ("germanic", "neolithic"):
        "This sample represents Neolithic farming populations from the Germanic region. "
        "Associated with the Linearbandkeramik (LBK) and subsequent Neolithic cultures of Central Europe.",

    ("germanic", "chalcolithic"):
        "This sample represents Chalcolithic populations from the Germanic region. "
        "Associated with Corded Ware and Bell Beaker cultures marking a major demographic shift.",

    ("germanic", "bronze_age"):
        "This sample represents Bronze Age populations of the Germanic region. "
        "Typical of the Unetice, Tumulus, and Urnfield cultural complexes of Central Europe.",

    ("germanic", "iron_age"):
        "This sample represents early Iron Age Germanic populations. "
        "Associated with pre-Roman Germanic tribes and the transition from Bronze Age traditions.",

    ("germanic", "roman"):
        "This sample represents populations from the Germanic region during the Roman period. "
        "Typical of communities along or beyond the Roman frontier (Limes), influenced by Roman contact.",

    ("germanic", "late_antique"):
        "This sample represents Migration Period populations from the Germanic region. "
        "Associated with the movement of Germanic groups during the decline of the Western Roman Empire.",

    ("germanic", "medieval"):
        "This sample represents Early Medieval Continental Germanic populations. "
        "Typical of Frankish, Saxon, or related Germanic communities in early medieval Europe.",

    ("central_europe", "neolithic"):
        "This sample represents Neolithic farming populations from Central Europe. "
        "Associated with the Linearbandkeramik (LBK) expansion and subsequent Central European farming cultures.",

    ("central_europe", "bronze_age"):
        "This sample represents Bronze Age populations from Central Europe. "
        "Typical of the Unetice, Tumulus, and Urnfield cultures that dominated Central Europe in this period.",

    ("central_europe", "iron_age"):
        "This sample represents Iron Age Celtic populations from Central Europe. "
        "Associated with Hallstatt and La Tène cultures, precursors to historically attested Celtic societies.",

    ("central_europe", "roman"):
        "This sample represents populations from Central Europe during the Roman period. "
        "Typical of communities in or near Roman provinces such as Pannonia, Noricum, or Raetia.",

    ("central_europe", "medieval"):
        "This sample represents medieval populations of Central Europe. "
        "Typical of communities in the Bohemian, Polish, or Pannonian cultural sphere.",

    ("eastern_europe", "bronze_age"):
        "This sample represents Steppe Bronze Age populations from Eastern Europe. "
        "Associated with Yamnaya and Corded Ware cultures that had a major demographic impact on Europe.",

    ("eastern_europe", "iron_age"):
        "This sample represents Iron Age populations from Eastern Europe, including Scythian-related groups. "
        "Typical of steppe-adjacent pastoral and semi-nomadic societies.",

    ("eastern_europe", "medieval"):
        "This sample represents medieval Slavic or related populations of Eastern Europe. "
        "Associated with the spread of Slavic-speaking communities across the region.",

    ("baltic", "neolithic"):
        "This sample represents Neolithic populations from the Baltic region. "
        "Associated with Comb Ceramic and related cultures distinct from the LBK farming expansion.",

    ("baltic", "bronze_age"):
        "This sample represents Bronze Age populations from the Baltic region. "
        "Typical of communities influenced by Corded Ware and steppe-derived cultures.",

    ("baltic", "iron_age"):
        "This sample represents Iron Age Baltic populations. "
        "Associated with early Baltic-speaking tribal groups ancestral to modern Latvians and Lithuanians.",

    ("iberia", "neolithic"):
        "This sample represents Neolithic farming populations from the Iberian Peninsula. "
        "Associated with early Mediterranean farming communities that spread along the western coastline.",

    ("iberia", "chalcolithic"):
        "This sample represents Chalcolithic populations of the Iberian Peninsula. "
        "Associated with complex societies such as Los Millares, known for megalithic monuments and early metallurgy.",

    ("iberia", "bronze_age"):
        "This sample represents Bronze Age populations of the Iberian Peninsula. "
        "Typical of El Argar and related Bronze Age cultures.",

    ("iberia", "iron_age"):
        "This sample represents Iron Age Celtic populations of the Iberian Peninsula. "
        "Associated with Celtiberian and Iberian tribal societies prior to Roman conquest.",

    ("iberia", "roman"):
        "This sample represents Hispano-Roman populations of the Iberian Peninsula. "
        "Typical of communities in the Roman province of Hispania.",

    ("iberia", "medieval"):
        "This sample represents medieval populations of the Iberian Peninsula. "
        "Associated with the complex mosaic of Christian, Muslim, and Jewish communities of medieval Iberia.",

    ("italy", "neolithic"):
        "This sample represents Neolithic farming populations from Italy. "
        "Associated with early Neolithic cultures that spread from the Adriatic into peninsular Italy.",

    ("italy", "bronze_age"):
        "This sample represents Bronze Age populations from Italy. "
        "Typical of Terramare and related Bronze Age cultures of the Italian Peninsula.",

    ("italy", "iron_age"):
        "This sample represents Iron Age populations from Italy before Roman unification. "
        "Associated with Italic peoples including Latins, Sabines, and Etruscans.",

    ("italy", "roman"):
        "This sample represents Roman Imperial-era populations from Italy. "
        "Typical of the cosmopolitan center of the Roman Empire, reflecting diverse population origins.",

    ("italy", "late_antique"):
        "This sample represents Late Antique populations of Italy. "
        "Associated with the transition from Roman rule to Ostrogothic and Byzantine control.",

    ("italy", "medieval"):
        "This sample represents medieval populations of Italy. "
        "Typical of communities influenced by Lombard, Frankish, and Byzantine cultural traditions.",

    ("balkans", "neolithic"):
        "This sample represents Neolithic farming populations from the Balkans. "
        "Associated with the earliest farming cultures in Europe, including Starcevo-Koros and Vinca.",

    ("balkans", "chalcolithic"):
        "This sample represents Chalcolithic populations from the Balkans. "
        "Associated with the Vinca and Cucuteni cultures, known for early copper use and proto-urban settlements.",

    ("balkans", "bronze_age"):
        "This sample represents Bronze Age populations from the Balkans. "
        "Typical of diverse Bronze Age cultures, including precursors to Thracians and Illyrians.",

    ("balkans", "iron_age"):
        "This sample represents Iron Age populations from the Balkans. "
        "Associated with Thracian, Illyrian, and Dacian tribal societies of the pre-Roman period.",

    ("balkans", "classical"):
        "This sample represents Classical or Hellenistic populations from the Balkan region. "
        "Associated with ancient Greek city-states and the spread of Hellenistic culture after Alexander.",

    ("balkans", "roman"):
        "This sample represents Roman-era populations from the Balkans. "
        "Typical of communities in Roman provinces such as Moesia, Thracia, and Macedonia.",

    ("balkans", "late_antique"):
        "This sample represents Late Antique or Early Byzantine populations of the Balkans. "
        "Associated with the transition from Roman to Byzantine administration and early Christianization.",

    ("balkans", "medieval"):
        "This sample represents Byzantine or medieval Balkan populations. "
        "Typical of communities within the Eastern Roman (Byzantine) cultural and political sphere.",

    ("anatolia", "neolithic"):
        "This sample represents Anatolian Neolithic farmers, a key ancestral source for European populations. "
        "Associated with the first farming communities of western Asia that later spread agriculture into Europe.",

    ("anatolia", "chalcolithic"):
        "This sample represents Chalcolithic populations from Anatolia. "
        "Associated with early metalworking societies and proto-urban centers of western Asia.",

    ("anatolia", "bronze_age"):
        "This sample represents Bronze Age populations from Anatolia. "
        "Associated with the Hittite Empire and related Bronze Age states of the ancient Near East.",

    ("anatolia", "iron_age"):
        "This sample represents Iron Age populations from Anatolia. "
        "Associated with post-Hittite Neo-Hittite states, Phrygian, and Lydian cultures.",

    ("anatolia", "classical"):
        "This sample represents Classical or Hellenistic populations from Anatolia. "
        "Associated with Hellenistic kingdoms such as Pergamon and Bithynia.",

    ("anatolia", "roman"):
        "This sample represents Roman-era populations from Anatolia. "
        "Typical of communities in the Roman provinces of Asia Minor.",

    ("anatolia", "late_antique"):
        "This sample represents Late Antique or Byzantine populations from Anatolia. "
        "Associated with the Byzantine heartland and the Christianization of the eastern Mediterranean.",

    ("anatolia", "medieval"):
        "This sample represents Byzantine or early Seljuk medieval populations from Anatolia. "
        "Typical of communities during the transition from Byzantine to Turkic cultural spheres.",

    ("levant", "prehistoric"):
        "This sample represents Natufian or Epipaleolithic hunter-gatherers from the Levant. "
        "Associated with communities ancestral to the world's first farmers.",

    ("levant", "neolithic"):
        "This sample represents Neolithic farming populations from the Levant. "
        "Associated with Pre-Pottery and Pottery Neolithic cultures of the southern Levant, among the earliest farmers.",

    ("levant", "chalcolithic"):
        "This sample represents Chalcolithic populations from the Levant. "
        "Associated with the Ghassulian and related Chalcolithic cultures of the southern Levant.",

    ("levant", "bronze_age"):
        "This sample represents Bronze Age Canaanite populations from the Levant. "
        "Typical of city-state-based urban societies in the Bronze Age southern Levant.",

    ("levant", "iron_age"):
        "This sample represents Iron Age populations from the Levant. "
        "Associated with Iron Age polities including Israelite, Phoenician, and Philistine communities.",

    ("levant", "roman"):
        "This sample represents Roman-era populations from the Levant. "
        "Typical of communities in the Roman province of Judaea / Syria Palaestina.",

    ("levant", "late_antique"):
        "This sample represents Late Antique or Byzantine populations from the Levant. "
        "Associated with Byzantine administration of the eastern Mediterranean prior to the Islamic conquests.",

    ("levant", "medieval"):
        "This sample represents medieval populations from the Levant. "
        "Associated with the transition to Islamic rule and subsequent Crusader-era communities.",

    ("mesopotamia", "neolithic"):
        "This sample represents early farming populations from Mesopotamia. "
        "Associated with Halaf and Ubaid cultures among the earliest complex societies of the ancient world.",

    ("mesopotamia", "bronze_age"):
        "This sample represents Bronze Age populations from Mesopotamia. "
        "Associated with Sumerian, Akkadian, and Babylonian civilizations of ancient Iraq.",

    ("mesopotamia", "iron_age"):
        "This sample represents Iron Age populations from Mesopotamia. "
        "Associated with the Assyrian and Neo-Babylonian empires.",

    ("mesopotamia", "medieval"):
        "This sample represents medieval populations from Mesopotamia. "
        "Associated with early Islamic communities in the Abbasid heartland.",

    ("iran", "prehistoric"):
        "This sample represents Zagros Mountains hunter-gatherers from western Iran. "
        "One of the key ancestral source populations for later Iranian and Caucasian gene pools.",

    ("iran", "neolithic"):
        "This sample represents Neolithic farming populations from the Zagros region of Iran. "
        "Associated with early farming communities distinct from Anatolian and Levantine Neolithic traditions.",

    ("iran", "bronze_age"):
        "This sample represents Bronze Age populations from Iran. "
        "Associated with early Iranian Bronze Age societies and interactions with the BMAC culture of Central Asia.",

    ("iran", "iron_age"):
        "This sample represents Iron Age populations from Iran. "
        "Associated with the emergence of Iranian-speaking peoples and early empires such as the Medes.",

    ("iran", "roman"):
        "This sample represents Parthian or Sassanid-era populations from Iran. "
        "Typical of communities in the Parthian and Sassanid empires, contemporaries of the Roman world.",

    ("iran", "medieval"):
        "This sample represents early Islamic medieval populations from Iran. "
        "Associated with the Islamization of Iran and the emergence of Persian Islamic civilization.",

    ("caucasus", "prehistoric"):
        "This sample represents Caucasian hunter-gatherers (CHG). "
        "Associated with the Caucasian hunter-gatherer ancestry component that contributed to later Bronze Age steppe peoples.",

    ("caucasus", "neolithic"):
        "This sample represents Neolithic populations from the South Caucasus. "
        "Associated with early farming and pastoral communities of the Caucasian highlands.",

    ("caucasus", "chalcolithic"):
        "This sample represents Chalcolithic populations from the South Caucasus. "
        "Associated with early copper-working societies of Armenia, Georgia, and Azerbaijan.",

    ("caucasus", "bronze_age"):
        "This sample represents Bronze Age populations from the South Caucasus. "
        "Associated with the Kura-Araxes culture, an influential Bronze Age complex spanning the Caucasus region.",

    ("caucasus", "iron_age"):
        "This sample represents Iron Age populations from the South Caucasus. "
        "Associated with the Kingdom of Urartu and related Iron Age cultures.",

    ("caucasus", "medieval"):
        "This sample represents medieval populations from the South Caucasus. "
        "Typical of communities in medieval Armenian, Georgian, or Caucasian Albanian kingdoms.",

    ("north_africa", "prehistoric"):
        "This sample represents Mesolithic hunter-gatherers from North Africa. "
        "Associated with Capsian and related cultures of the prehistoric Maghreb and Nile Valley.",

    ("north_africa", "neolithic"):
        "This sample represents Neolithic populations from North Africa. "
        "Associated with early pastoralist and farming communities of the Green Sahara period.",

    ("north_africa", "bronze_age"):
        "This sample represents Bronze Age populations from North Africa. "
        "Typical of communities in the broader North African Bronze Age horizon.",

    ("north_africa", "iron_age"):
        "This sample represents Iron Age populations from North Africa. "
        "Associated with Phoenician colonial settlements and indigenous Berber cultures.",

    ("north_africa", "roman"):
        "This sample represents Roman-era populations from North Africa. "
        "Typical of communities in the Roman provinces of Africa Proconsularis and Numidia.",

    ("north_africa", "medieval"):
        "This sample represents medieval Islamic populations from North Africa. "
        "Associated with the Arabization and Islamization of the Maghreb following the 7th-century conquest.",

    ("central_asia", "bronze_age"):
        "This sample represents Bronze Age steppe populations from Central Asia. "
        "Associated with Andronovo, Sintashta, and related cultures with far-reaching genetic influence.",

    ("central_asia", "iron_age"):
        "This sample represents Iron Age populations from Central Asia. "
        "Associated with Scythian, Saka, and related nomadic cultures of the Eurasian steppe.",

    ("central_asia", "medieval"):
        "This sample represents medieval populations from Central Asia. "
        "Associated with the diverse Silk Road communities including Sogdian, Turkic, and Mongolian influences.",
}

# ---------------------------------------------------------------------------
# Token-specific culture/description overrides (checked before group lookup)
# ---------------------------------------------------------------------------

_TOKEN_OVERRIDES: dict[str, dict[str, dict[str, str]]] = {
    "viking": {
        "british_isles": {
            "culture": "Norse / Viking",
            "description": (
                "This sample represents Norse settlers or raiders active in Scotland or northern Britain. "
                "Associated with seafaring Norse populations from Scandinavia active across the North Atlantic."
            ),
        },
        "scandinavia": {
            "culture": "Norse / Viking",
            "description": (
                "Seafaring Norse populations active across the North Atlantic and Baltic regions. "
                "Associated with raiding, trade, and settlement from Scandinavia during the Viking Age."
            ),
        },
        "_default": {
            "culture": "Norse / Viking",
            "description": (
                "This sample represents populations from the Viking Age. "
                "Associated with Norse cultural traditions of maritime activity and long-distance trade."
            ),
        },
    },
    "saxon": {
        "british_isles": {
            "culture": "Anglo-Saxon",
            "description": (
                "This sample represents Anglo-Saxon populations of early medieval England. "
                "Associated with Germanic migrants from the continent who settled in post-Roman Britain."
            ),
        },
        "germanic": {
            "culture": "Continental Saxon / Germanic",
            "description": (
                "This sample represents Continental Saxon populations of early medieval Germany or the Netherlands. "
                "Typical of Germanic communities during the Carolingian and Migration periods."
            ),
        },
        "_default": {
            "culture": "Saxon / Germanic",
            "description": (
                "This sample represents Saxon populations of the early medieval period. "
                "Associated with Continental Germanic communities and their settlement patterns."
            ),
        },
    },
    "anglosaxon": {
        "_default": {
            "culture": "Anglo-Saxon",
            "description": (
                "This sample represents Anglo-Saxon populations of early medieval England. "
                "Associated with Germanic migrants from the continent who settled in post-Roman Britain."
            ),
        },
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_sample(name: str) -> dict[str, str]:
    """
    Return historical enrichment metadata for a G25 sample name.

    Returns a dict with keys:
        period, date_range, area, culture, description
    All values are strings; empty string when not determined.

    This function is deterministic and performs no I/O.
    """
    tokens = _tokenize(name)
    if not tokens:
        return {"period": "", "date_range": "", "area": "", "culture": "", "description": ""}

    country = tokens[0]
    tokens_lc = [t.lower() for t in tokens]
    tokens_lc_set = set(tokens_lc)

    # Period detection (skip first country token)
    period_label, date_range, period_group = _detect_period(tokens_lc[1:])

    # Country group
    country_group = _COUNTRY_TO_GROUP.get(country, "")

    # Area: base country area + extracted locality
    base_area = _COUNTRY_AREA.get(country, country)
    locality = _extract_locality(tokens)
    area = f"{locality}, {base_area}" if locality else base_area

    # Check token-specific overrides first (viking, saxon, etc.)
    culture = ""
    description = ""
    for override_token, group_map in _TOKEN_OVERRIDES.items():
        if override_token in tokens_lc_set:
            target = group_map.get(country_group) or group_map.get("_default", {})
            culture = target.get("culture", "")
            description = target.get("description", "")
            break

    # Fall back to (country_group, period_group) lookup
    if not culture and country_group and period_group and period_group != "unknown":
        culture = _CULTURE_MAP.get((country_group, period_group), "")
    if not description and country_group and period_group and period_group != "unknown":
        description = _DESCRIPTION_MAP.get((country_group, period_group), "")

    return {
        "period": period_label,
        "date_range": date_range,
        "area": area,
        "culture": culture,
        "description": description,
    }


def has_enrichment(e: dict[str, str]) -> bool:
    """Return True if the enrichment dict contains at least one meaningful field."""
    return any(e.get(k) for k in ("period", "culture", "area"))
