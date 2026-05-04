"""Extract job requirements from free-text job descriptions.

Strategy (applied in order, stops when enough items are found):

1.  Locate a labelled requirements / qualifications section and extract its
    bullet-point items.
2.  Scan all bullet / list items anywhere in the text for requirement-indicator
    words.
3.  Fall back to tech-keyword matching via ``extract_skills``.

Returned value: comma-separated requirement phrases, suitable for storing in
the ``skills`` column and splitting back for display.
"""

from __future__ import annotations

import re

from web_scraping.skill_extractor import extract_skills

# ── Section headers that OPEN a requirements block ─────────────────────────
_REQ_HEADER = re.compile(
    r"^(?:"
    r"requirements?"
    r"|qualifications?"
    r"|what\s+you(?:'ll|'d)?\s+(?:need|bring|have|offer)"
    r"|what\s+we(?:'re)?\s+looking\s+for"
    r"|what\s+you\s+should\s+(?:have|know|bring)"
    r"|minimum\s+qualifications?"
    r"|preferred\s+qualifications?"
    r"|basic\s+qualifications?"
    r"|required\s+qualifications?"
    r"|must[\s\-]have"
    r"|key\s+(?:skills?|competencies|requirements?)"
    r"|skills?\s+(?:required|needed|and\s+experience|&\s+experience)"
    r"|experience\s+(?:required|needed|and\s+qualifications?)"
    r"|about\s+you"
    r"|you\s+(?:have|bring|are|will\s+bring|will\s+have)"
    r"|ideal\s+candidate"
    r"|candidate\s+(?:requirements?|profile)"
    r"|technical\s+(?:requirements?|skills?)"
    r"|core\s+(?:skills?|competencies|requirements?)"
    r"|who\s+you\s+are"
    r"|your\s+(?:background|profile|skills?|experience)"
    r")[\s:·\-–—]*$",
    re.IGNORECASE,
)

# ── Section headers that CLOSE a requirements block ────────────────────────
_STOP_HEADER = re.compile(
    r"^(?:"
    r"responsibilities|what\s+you(?:'ll)?\s+do|your\s+role|day[\s\-]to[\s\-]day"
    r"|in\s+this\s+role|about\s+the\s+(?:company|role|job|position|team)"
    r"|about\s+(?:us|the\s+company)|the\s+company|our\s+(?:company|story|mission)"
    r"|who\s+we\s+are|benefits?|perks?|compensation|salary|what\s+we\s+offer"
    r"|we\s+offer|nice[\s\-]to[\s\-]have|bonus\s+(?:points?|skills?|if\s+you)"
    r"|additional\s+(?:qualifications?|skills?)"
    r"|plus(?:\s+if|\s+points?)?"
    r")[\s:·\-–—]*$",
    re.IGNORECASE,
)

# ── Bullet / list item — captures the text after the marker ───────────────
_BULLET = re.compile(
    r"^\s*(?:[•\-\*\u2022\u2023\u25E6\u2043\u2219›‣⁃◦–—]|\d+[\.\):])\s+(.+)"
)

# ── Words that strongly signal a line describes a candidate requirement ────
_REQ_WORDS = re.compile(
    r"\b(?:"
    r"experience|year(?:s)?\s+of|proficien|familiar(?:ity)?|knowledge(?:\s+of)?"
    r"|degree|bachelor|master|phd|msc|mba|diploma|certified|certification"
    r"|strong|proven|solid|demonstrated|hands[\s\-]on|working\s+knowledge"
    r"|required|must\s+(?:have|be)|should\s+have|ability\s+to"
    r"|understanding(?:\s+of)?|skill(?:ed|s)?|competenc|expertise"
    r"|track\s+record|background\s+in|comfortable\s+with|passion(?:ate)?"
    r"|previous\s+experience|prior\s+experience|minimum\s+\d"
    r")\b",
    re.IGNORECASE,
)

_MAX_ITEM_LEN = 120   # chars — long enough to preserve meaning


def _clean(text: str) -> str:
    """Normalise whitespace, strip trailing punctuation, capitalise."""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"[.;]+$", "", text).strip()
    if text and not text[0].isupper():
        text = text[0].upper() + text[1:]
    return text[:_MAX_ITEM_LEN]


def _from_requirements_section(lines: list[str]) -> list[str]:
    """Find the first requirements-like section and return its bullet items."""
    inside = False
    blank_streak = 0
    items: list[str] = []

    for line in lines:
        if not line:
            if inside:
                blank_streak += 1
                if blank_streak > 2:
                    break
            continue
        else:
            blank_streak = 0

        if not inside:
            if _REQ_HEADER.match(line):
                inside = True
            continue

        # Inside section — check for a stop-header
        if _STOP_HEADER.match(line):
            break

        m = _BULLET.match(line)
        if m:
            cleaned = _clean(m.group(1))
            if cleaned and len(cleaned) > 5:
                items.append(cleaned)
        elif _REQ_WORDS.search(line) and len(line) < 200:
            # Non-bulleted requirement line (some posts don't use bullets)
            cleaned = _clean(line)
            if cleaned and len(cleaned) > 5:
                items.append(cleaned)

    return items


def _from_all_bullets(lines: list[str], exclude: set[str]) -> list[str]:
    """Return all bullet items anywhere in the text that look like requirements."""
    items: list[str] = []
    for line in lines:
        m = _BULLET.match(line)
        if m:
            content = _clean(m.group(1))
            if content and content not in exclude and _REQ_WORDS.search(content):
                items.append(content)
    return items


def extract_requirements(text: str, max_items: int = 20) -> str:
    """Extract job requirements from free-text description.

    Returns a comma-separated list of up to *max_items* requirement phrases.
    Suitable for storing in the ``skills`` column.
    """
    if not text:
        return ""

    lines = [ln.strip() for ln in text.splitlines()]

    # Strategy 1 — requirements section bullets
    items = _from_requirements_section(lines)

    # Strategy 2 — requirement-like bullets anywhere in the text
    if len(items) < 3:
        extra = _from_all_bullets(lines, exclude=set(items))
        items = items + extra

    # Strategy 3 — tech-keyword fallback
    if not items:
        return extract_skills(text)

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return ", ".join(deduped[:max_items])
