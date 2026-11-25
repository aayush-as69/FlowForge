"""Plain-language explanation of what a workflow decided and why, built only from facts already recorded.

Nothing here calls a model: every sentence is derived from stored policy results, vendor offers, the decision trace,
approvals and exceptions, so an explanation can always be traced back to the audit trail.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Approval, Workflow, WorkflowException

_ORDINAL_STATUS = {"pass": "passed", "warn": "passed with a flag", "fail": "failed", "skipped": "not applicable"}


def _vendor_reasons(selected: dict, eligible: list[dict], days: int | None, budget: int | None) -> list[dict]:
    """Why the winner won, as checkable statements (ok=True means it counts in the vendor's favour)."""
    out: list[dict] = []
    others = [o for o in eligible if o["vendor_id"] != selected["vendor_id"]]
    if others:
        runner_up = max(others, key=lambda o: o["score"])
        out.append({"ok": True, "text": f"Highest overall score ({selected['score']} vs {runner_up['score']} for {runner_up['name']})"})
    else:
        out.append({"ok": True, "text": "Only eligible vendor"})
    priced = [o for o in eligible if o.get("total")]
    if priced and selected.get("total") == min(o["total"] for o in priced) and len(priced) > 1:
        out.append({"ok": True, "text": "Lowest total price among eligible vendors"})
    if len(eligible) > 1 and selected["delivery_days"] == min(o["delivery_days"] for o in eligible):
        out.append({"ok": True, "text": f"Fastest delivery ({selected['delivery_days']} days)"})
    if days is not None:
        ok = selected["delivery_days"] <= days
        out.append({"ok": ok, "text": f"Delivery in {selected['delivery_days']} days "
                                      f"{'meets' if ok else 'misses'} the required date ({days} days away)"})
    if budget and selected.get("total") is not None:
        ok = selected["total"] <= budget
        out.append({"ok": ok, "text": f"Total {'within' if ok else 'over'} the stated budget"})
    out.append({"ok": bool(selected["approved"]), "text": "Approved vendor" if selected["approved"] else "Vendor is not on the approved list"})
    delta = selected.get("price_delta_pct")
    if delta is not None:
        out.append({"ok": delta <= 10, "text": f"Price is {abs(delta)}% {'above' if delta > 0 else 'below'} its historical average"})
    return out


def _rejected(selected: dict, offers: list[dict]) -> list[dict]:
    rows = []
    for o in offers:
        if o["vendor_id"] == selected["vendor_id"]:
            continue
        if not o["eligible"]:
            why = "; ".join(o["reasons"]) or "Not eligible"
        else:
            bits = [f"Scored lower ({o['score']} vs {selected['score']})"]
            if o.get("total") and selected.get("total") and o["total"] > selected["total"]:
                bits.append(f"{round((o['total'] - selected['total']) / selected['total'] * 100)}% more expensive")
            if o["delivery_days"] > selected["delivery_days"]:
                bits.append(f"{o['delivery_days'] - selected['delivery_days']} days slower")
            why = "; ".join(bits)
        rows.append({"vendor": o["name"], "eligible": o["eligible"], "score": o["score"], "why": why})
    return rows


def explain(db: Session, wf: Workflow) -> dict:
    ctx = wf.context or {}
    req = wf.request
    policy = ctx.get("policy_report_final") or ctx.get("policy_report")
    offers = ctx.get("offers") or []
    selected = ctx.get("selected")
    days = None
    if req is not None and req.required_date and wf.created_at:
        days = max((req.required_date - wf.created_at.date()).days, 0)

    vendor = None
    if selected and offers:
        eligible = [o for o in offers if o["eligible"]]
        vendor = {"selected": selected["name"], "total": selected.get("total"), "score": selected["score"],
                  "reasons": _vendor_reasons(selected, eligible, days, req.budget if req else None),
                  "rejected": _rejected(selected, offers), "recommendation": ctx.get("recommendation")}

    decision = ctx.get("decision")
    autonomy = None
    if decision:
        autonomy = {"level": decision["level"], "outcome": decision["outcome"], "reasons": decision["reasons"],
                    "trace": decision["trace"], "required_role": decision.get("required_role"),
                    "plain": {1: "Executed automatically: low impact, every policy satisfied",
                              2: "Prepared automatically, then checked by a person before execution",
                              3: "High impact: a person has to make the decision"}.get(decision["level"], decision["outcome"])}

    approvals = db.query(Approval).filter(Approval.workflow_id == wf.id).order_by(Approval.id).all()
    exceptions = db.query(WorkflowException).filter(WorkflowException.workflow_id == wf.id).order_by(WorkflowException.id).all()
    human = [{"approval_id": a.id, "title": a.title, "status": a.status, "by": a.decided_by, "role": a.decided_by_role,
              "note": a.decision_note, "at": a.decided_at, "asked_at": a.created_at,
              "waited_s": int((a.decided_at - a.created_at).total_seconds()) if a.decided_at and a.created_at else None}
             for a in approvals]
    recovered = [{"code": e.code, "message": e.message, "status": e.status, "resolution": e.resolution, "attempts": e.attempts}
                 for e in exceptions]

    steps = []
    if wf.steps:
        for s in sorted(wf.steps, key=lambda s: s.position):
            steps.append({"key": s.key, "name": s.name, "status": s.status, "decision": s.decision, "reason": s.reason})

    headline = _headline(wf, vendor, autonomy, human, recovered)
    return {
        "workflow_id": wf.id, "status": wf.status, "headline": headline,
        "extraction": {"engine": req.extraction_engine, "confidence": req.confidence, "corrected": req.corrected,
                       "notes": req.extraction_notes} if req else None,
        "policy": {"passed": policy["passed"], "required_role": policy.get("required_role"),
                   "results": [{"key": r["key"], "name": r.get("name") or r["key"], "status": r["status"],
                                "label": _ORDINAL_STATUS.get(r["status"], r["status"]), "message": r.get("message")}
                               for r in policy["results"]]} if policy else None,
        "vendor": vendor, "autonomy": autonomy, "human": human, "exceptions": recovered, "steps": steps,
    }


def _headline(wf: Workflow, vendor, autonomy, human, recovered) -> str:
    parts = []
    if vendor:
        parts.append(f"{vendor['selected']} was selected")
    if autonomy:
        parts.append(autonomy["plain"].lower() if autonomy["level"] > 1 else "it ran without human involvement")
    decided = [h for h in human if h["status"] != "pending"]
    if decided:
        parts.append(f"{len(decided)} human decision(s) recorded")
    if recovered:
        parts.append(f"{len(recovered)} exception(s) handled")
    state = {"completed": "Completed", "failed": "Failed", "waiting_human": "Waiting for a person", "cancelled": "Cancelled"}.get(wf.status, "In progress")
    return f"{state}. " + ("; ".join(parts).capitalize() + "." if parts else "Nothing has been decided yet.")
