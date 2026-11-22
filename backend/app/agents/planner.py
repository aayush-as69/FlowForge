"""Workflow planner: turns an understood request into an explicit, inspectable plan."""
from __future__ import annotations

from app.services.policy_engine import inr


def build_plan(wf) -> list[dict]:
    r = wf.request
    if r is None:
        return []
    when = f" delivering by {r.required_date_text or r.required_date}" if r.required_date else ""
    return [
        {"step": "ingest", "intent": f"Register the {r.source.replace('_', ' ')} request and archive the original input"},
        {"step": "understand", "intent": f"Confirm extracted data ({r.quantity}× {r.category}, budget {inr(r.budget)}) and enrich with requester context from CRM"},
        {"step": "policy_check", "intent": "Validate category, budget, quantity, documentation and HR requirement against configured policies"},
        {"step": "vendor_evaluation", "intent": f"Compare approved vendors on price, delivery{when}, rating, warranty and reliability; flag price anomalies"},
        {"step": "decision", "intent": "Apply decision rules to choose Level 1 auto-execute, Level 2 review or Level 3 human decision"},
        {"step": "approval", "intent": "Request human approval only if the decision rules demand it"},
        {"step": "purchase_order", "intent": "Confirm vendor availability, check budget and issue the purchase order"},
        {"step": "erp_update", "intent": "Post the PO to the ERP and commit the spend in accounting"},
        {"step": "fulfillment", "intent": "Send the order to the vendor, capture confirmation/ETA and notify the requester"},
        {"step": "verification", "intent": "Verify delivery date, budget, ERP/accounting references and invoice three-way match"},
        {"step": "complete", "intent": "Close the request and record the final outcome"},
    ]
