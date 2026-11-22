"""AI request understanding: free text / email / form → structured procurement request.

Primary path: an LLM with a strict JSON contract, validated by Pydantic.
Fallback path: a deterministic rule-based parser (always available, used in the offline demo)."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.agents import llm

CATEGORY_KEYWORDS = {
    "laptop": ["laptop", "notebook", "macbook", "thinkpad"],
    "monitor": ["monitor", "display", "screen"],
    "peripherals": ["keyboard", "mouse", "headset", "webcam", "dock", "docking"],
    "furniture": ["chair", "desk", "furniture"],
    "software": ["license", "licence", "subscription", "software", "seat"],
    "networking": ["switch", "router", "access point", "firewall", "network"],
    "server": ["server", "rack"],
}
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


class Extracted(BaseModel):
    item: str | None = None
    category: str | None = None
    quantity: int | None = Field(default=None, ge=1, le=1000)
    purpose: str | None = None
    required_date: date | None = None
    required_date_text: str | None = None
    budget: int | None = Field(default=None, ge=0)
    requirements: str | None = None
    requester_name: str | None = None

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        return v.lower().strip() if v else v


class ExtractionResult(BaseModel):
    fields: Extracted
    confidence: float
    engine: str
    notes: list[str] = []


def classify(text: str) -> str | None:
    t = text.lower()
    for cat, words in CATEGORY_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(w)}s?\b", t) for w in words):
            return cat
    return None


def parse_amount(text: str) -> int | None:
    t = text.lower().replace("₹", " ₹ ")
    m = re.search(r"budget[^0-9₹]{0,25}(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|k)?", t)
    if not m:
        m = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|k)?", t)
    if not m:
        m = re.search(r"([\d,]+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|k)?\s*(?:rupees|inr)", t)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = m.group(2) or ""
    if unit.startswith(("lakh", "lac")):
        value *= 100_000
    elif unit.startswith("crore"):
        value *= 10_000_000
    elif unit == "k":
        value *= 1_000
    return int(value)


def parse_date(text: str, today: date) -> tuple[date | None, str | None]:
    t = text.lower()
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
    if m:
        try:
            return date.fromisoformat(m.group(1)), m.group(1)
        except ValueError:
            pass
    m = re.search(r"\b(next|this|coming)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", t)
    if m:
        target = WEEKDAYS.index(m.group(2))
        delta = (target - today.weekday()) % 7 or 7
        if m.group(1) in ("next", None) and delta < 3 and m.group(1) == "next":
            delta += 7  # "next Monday" said on a Saturday/Sunday means the following week
        return today + timedelta(days=delta), (m.group(0).strip())
    if "tomorrow" in t:
        return today + timedelta(days=1), "tomorrow"
    m = re.search(r"in\s+(\d+)\s+(day|week)s?", t)
    if m:
        return today + timedelta(days=int(m.group(1)) * (7 if m.group(2) == "week" else 1)), m.group(0)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", t)
    if m:
        month, day = MONTHS[m.group(2)], int(m.group(1))
        year = today.year + (1 if (month, day) < (today.month, today.day) else 0)
        try:
            return date(year, month, day), m.group(0)
        except ValueError:
            pass
    if re.search(r"\b(asap|urgent|immediately)\b", t):
        return today + timedelta(days=2), "ASAP"
    if "next week" in t:
        return today + timedelta(days=7), "next week"
    return None, None


def _labelled(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    pat = re.compile(r"^\s*(item|purpose|quantity|qty|required date|needed by|required by|budget|requester|from|"
                     r"additional requirements?|requirements?|notes|subject)\s*:\s*(.+?)\s*$", re.I | re.M)
    for m in pat.finditer(text):
        out.setdefault(m.group(1).lower(), m.group(2))
    return out


def heuristic_extract(text: str, today: date | None = None) -> ExtractionResult:
    today = today or date.today()
    notes: list[str] = []
    labelled = _labelled(text)
    body = text
    item_text = labelled.get("item") or labelled.get("subject") or text
    category = classify(item_text) or classify(text)

    quantity = None
    raw_q = labelled.get("quantity") or labelled.get("qty")
    if raw_q and raw_q.strip().isdigit():
        quantity = int(raw_q.strip())
    if quantity is None and category:
        kw = "|".join(w for w in CATEGORY_KEYWORDS[category])
        m = re.search(rf"\b(\d+|{'|'.join(NUMBER_WORDS)})\b\s*(?:x|units?|pcs|pieces|new|more)?\s*(?:[\w\-]+\s+){{0,2}}?(?:{kw})s?\b",
                      text.lower())
        if m:
            tok = m.group(1)
            quantity = int(tok) if tok.isdigit() else NUMBER_WORDS.get(tok)
    if quantity is None and category:
        quantity = 1
        notes.append("Quantity not stated; assumed 1")

    budget = parse_amount(labelled["budget"]) if "budget" in labelled else None
    budget = budget if budget is not None else parse_amount(body)
    date_src = labelled.get("required date") or labelled.get("needed by") or labelled.get("required by") or body
    required_date, date_text = parse_date(date_src, today)

    purpose = labelled.get("purpose")
    low = text.lower()
    if not purpose:
        if re.search(r"new (employee|hire|joiner)|joining", low):
            purpose = "New employee"
        elif "replacement" in low or "replace" in low:
            purpose = "Replacement"
        elif re.search(r"\bteam expansion|new project\b", low):
            purpose = "Team expansion"
        else:
            m = re.search(r"\bfor (?:the |our )?([a-z&]+(?: [a-z&]+)? (?:team|department|office|floor|branch))\b", low)
            if m:
                purpose = f"For the {m.group(1)}"
    requirements = labelled.get("additional requirements") or labelled.get("additional requirement") or labelled.get("requirements") or labelled.get("notes")
    if not requirements:
        specs = re.findall(r"\b\d+\s?(?:gb|tb)\b|\bi[3579]\b|ryzen\s?\d|\bssd\b", low)
        requirements = ", ".join(dict.fromkeys(s.upper() for s in specs)) or None

    requester = labelled.get("requester") or labelled.get("from")
    if requester:
        requester = re.sub(r"<.*?>", "", requester).strip() or None

    item = labelled.get("item")
    if not item and category:
        # Preserve meaningful compound product names instead of collapsing "network switches" to "network".
        phrase_rules = [
            (r"\bnetwork\s+switch(?:es)?\b", "Network switches"),
            (r"\baccess\s+point(?:s)?\b", "Access points"),
            (r"\brack\s+server(?:s)?\b", "Rack servers"),
            (r"\bwireless\s+keyboard(?:\s+and\s+mouse)?\s+sets?\b", "Wireless keyboard and mouse sets"),
        ]
        for pattern, label in phrase_rules:
            if re.search(pattern, low):
                item = label
                break
        if not item:
            kw = "|".join(CATEGORY_KEYWORDS[category])
            nums = "|".join(NUMBER_WORDS)
            m = re.search(rf"\b(?:\d+|{nums})\s+((?:[\w\-]+\s+){{0,3}}?(?:{kw})s?(?:\s+(?:stations?|sets?|units?|licen[cs]es?|seats?))?)\b", low)
            item = m.group(1).strip().capitalize() if m else category.capitalize()

    fields = Extracted(item=item, category=category, quantity=quantity, purpose=purpose, required_date=required_date,
                       required_date_text=date_text, budget=budget, requirements=requirements, requester_name=requester)
    weights = {"category": 0.3, "quantity": 0.15, "budget": 0.25, "required_date": 0.2, "purpose": 0.1}
    confidence = sum(w for f, w in weights.items() if getattr(fields, f) is not None)
    if "quantity" in notes[0:1] and not raw_q:
        confidence -= 0.05
    if category is None:
        notes.append("Could not classify the requested item into a known category")
    if budget is None:
        notes.append("No budget found in the request")
    return ExtractionResult(fields=fields, confidence=round(max(confidence, 0.0), 2), engine="heuristic", notes=notes)


SYSTEM_PROMPT = (
    "You extract structured procurement requests. Return ONLY a JSON object with keys: item, category "
    f"(one of {sorted(CATEGORY_KEYWORDS)} or null), quantity (integer), purpose, required_date (ISO date or null), "
    "required_date_text, budget (integer INR; convert lakh/crore), requirements, requester_name. "
    "Use null when unknown. Never invent values."
)


def extract(text: str, today: date | None = None) -> ExtractionResult:
    today = today or date.today()
    if llm.available():
        data = llm.complete_json(SYSTEM_PROMPT, f"Today is {today.isoformat()}.\nRequest:\n{text}")
        if data:
            try:
                fields = Extracted.model_validate(data)
                base = heuristic_extract(text, today)
                # LLM output is validated, then gaps are filled by deterministic parsing
                merged = fields.model_copy(update={
                    k: v for k, v in base.fields.model_dump().items() if getattr(fields, k) is None and v is not None
                })
                score = sum(w for f, w in {"category": 0.3, "quantity": 0.15, "budget": 0.25, "required_date": 0.2, "purpose": 0.1}.items()
                            if getattr(merged, f) is not None)
                return ExtractionResult(fields=merged, confidence=round(score, 2), engine=llm.engine_name(), notes=base.notes)
            except ValidationError:
                pass
        result = heuristic_extract(text, today)
        result.notes.append("LLM extraction unavailable or invalid; used rule-based parser")
        return result
    return heuristic_extract(text, today)


def to_json(result: ExtractionResult) -> str:
    return json.dumps(result.model_dump(mode="json"))
