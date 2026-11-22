"""Natural-language explanations. Always grounded in the structured facts produced by the engines;
an optional LLM can add a reviewer-facing rationale on top but is never the source of truth."""
from __future__ import annotations

import json

from app.agents import llm
from app.services.policy_engine import inr


def vendor_recommendation(offers: list[dict], selected: dict, days: int | None) -> str:
    eligible = [o for o in offers if o["eligible"]]
    wins = []
    if selected["delivery_days"] == min(o["delivery_days"] for o in eligible):
        wins.append(f"the fastest delivery ({selected['delivery_days']} days)")
    if selected["reliability"] == max(o["reliability"] for o in eligible):
        wins.append(f"the highest reliability score ({selected['reliability']:g}%)")
    if selected["rating"] == max(o["rating"] for o in eligible):
        wins.append(f"the best rating ({selected['rating']})")
    if selected["warranty_years"] == max(o["warranty_years"] for o in eligible):
        wins.append(f"the longest warranty ({selected['warranty_years']} years)")
    if selected["unit_price"] == min(o["unit_price"] for o in eligible):
        wins.append(f"the lowest price ({inr(selected['unit_price'])})")
    text = f"{selected['name']} is recommended"
    if days is not None:
        text += f" because it satisfies the {days}-day delivery requirement"
        text += f" and has {', '.join(wins)}" if wins else ""
    elif wins:
        text += f" because it offers {', '.join(wins)}"
    else:
        text += " because it has the best weighted score across price, delivery, rating, warranty, reliability and compliance"
    cheaper = [o for o in eligible if o["unit_price"] < selected["unit_price"]]
    if cheaper:
        c = min(cheaper, key=lambda o: o["unit_price"])
        text += f", despite not having the lowest price ({c['name']} is {inr(c['unit_price'])} vs {inr(selected['unit_price'])})"
    text += "."
    out = [o for o in offers if not o["eligible"]]
    if out:
        text += " Excluded: " + "; ".join(f"{o['name']} ({'; '.join(o['reasons'])})" for o in out) + "."
    return text


def anomaly_review(details: dict, rejected: list[dict], budget: int | None, days: int | None) -> dict:
    total = details["unit_price"] * details.get("quantity", 1)
    hist_total = details["historical_avg"] * details.get("quantity", 1)
    premium = total - hist_total
    summary = (f"{details['vendor']} quoted {inr(details['unit_price'])} per unit, {details['delta']}% above its historical "
               f"average of {inr(details['historical_avg'])} (policy threshold {details['threshold']:g}%).")
    if rejected:
        why = " ".join(f"{r['vendor']}: {'; '.join(r['why'])}." for r in rejected)
        reason = f"FlowForge searched approved alternatives before escalating, but none could be substituted safely. {why}"
    else:
        reason = "FlowForge found no other approved vendor able to supply this request."
    within = budget is None or total <= budget
    recommendation = (
        f"Approve {details['vendor']}: it is the only option meeting the delivery and reliability requirements. "
        f"The premium of about {inr(premium)} over historical average "
        + ("stays within the approved budget." if within else "pushes the order over budget; consider Modify or Reject.")
    )
    risk = f"Medium — paying roughly {inr(premium)} above the historical benchmark for this vendor."
    return {"summary": summary, "reason": reason, "recommendation": recommendation, "risk": risk}


def ai_rationale(facts: dict) -> str | None:
    """Optional LLM-written rationale. Returns None when no LLM is configured."""
    return llm.complete_text(
        "You are an operations analyst. In 2 sentences, explain to an approver why this exception needs a decision. "
        "Use only the facts given.", json.dumps(facts, default=str))


def final_outcome(po: dict, vendor: str, humans: int, exceptions: int, auto_resolved: int) -> str:
    text = (f"Purchase order {po['po_number']} for {po['quantity']}× {po['item']} ({inr(po['total'])}) was issued to {vendor}, "
            f"posted to the ERP ({po['erp_ref']}) and committed in accounting ({po['accounting_ref']}). "
            f"Expected delivery {po['expected_delivery']}.")
    bits = []
    if exceptions:
        bits.append(f"{exceptions} exception(s) handled ({auto_resolved} resolved automatically)")
    bits.append(f"{humans} human decision(s)" if humans else "no human intervention required")
    return text + " " + "; ".join(bits).capitalize() + "."
