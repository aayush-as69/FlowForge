"""Replay proposed policy changes against past workflows without touching any data.

The replay reuses the production policy and decision engines on in-memory copies of the policies, so the answer to
"what would this change have done?" comes from exactly the code that would run for real. Nothing is written.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.decisions.engine import DecisionConfig, decide
from app.models import Policy, Workflow
from app.services import policy_engine

OUTCOMES = ("auto", "review", "human", "blocked", "exception")


class SimulationError(ValueError):
    pass


def _copy(p: Policy) -> SimpleNamespace:
    return SimpleNamespace(key=p.key, name=p.name, category=p.category, rule_type=p.rule_type, params=dict(p.params or {}),
                           severity=p.severity, enabled=p.enabled, id=p.id)


def apply_changes(policies: list[Policy], changes: list[dict]) -> list[SimpleNamespace]:
    """In-memory copies of the policies with the proposed edits applied (validated like a real edit)."""
    out = [_copy(p) for p in policies]
    by_id = {p.id: p for p in out}
    for change in changes:
        target = by_id.get(change.get("policy_id"))
        if target is None:
            raise SimulationError(f"Unknown policy {change.get('policy_id')}.")
        if change.get("params") is not None:
            problem = policy_engine.validate_params(target.rule_type, change["params"])
            if problem:
                raise SimulationError(f"{target.name}: {problem}")
            target.params = dict(change["params"])
        if change.get("enabled") is not None:
            target.enabled = bool(change["enabled"])
        if change.get("severity") is not None:
            if change["severity"] not in ("block", "warn"):
                raise SimulationError("Severity must be 'block' or 'warn'.")
            target.severity = change["severity"]
    return out


def _accept_overrides(report: policy_engine.PolicyReport, accepted: set[str]) -> None:
    for res in report.results:
        if res.key in accepted and res.status == "fail" and res.severity == "block":
            res.status, res.severity = "warn", "warn"


def classify(facts: dict, policies: list, *, accepted_blocks: set[str] | None = None, anomaly_accepted: bool = False) -> dict:
    """Outcome of one purchase under one set of policies."""
    report = policy_engine.evaluate(facts, policies)
    _accept_overrides(report, accepted_blocks or set())
    cfg = DecisionConfig.from_policies(policies)
    if not report.passed:
        return {"outcome": "blocked", "level": None, "needs_human": True,
                "reasons": [x.message for x in report.blocking]}
    delta = facts.get("price_delta_pct")
    if delta is not None and delta > cfg.anomaly_pct and not anomaly_accepted:
        return {"outcome": "exception", "level": None, "needs_human": True,
                "reasons": [f"Price is {delta}% above its historical average (limit {cfg.anomaly_pct}%)"]}
    result = decide({"amount": facts["total"], "budget": facts.get("budget"), "vendor_approved": facts["vendor"]["approved"],
                     "price_delta_pct": delta, "anomaly_accepted": anomaly_accepted, "grant": None}, report, cfg)
    return {"outcome": {1: "auto", 2: "review", 3: "human"}[result.level], "level": result.level,
            "needs_human": result.needs_human, "reasons": result.reasons}


def _facts_from(wf: Workflow) -> dict | None:
    ctx, req = wf.context or {}, wf.request
    sel = ctx.get("selected")
    if not sel or req is None:
        return None
    hr = next((x for x in (ctx.get("policy_report") or {}).get("results", []) if x["key"] == "hr_new_hire"), None)
    return {"category": req.category, "quantity": req.quantity, "budget": req.budget, "purpose": req.purpose,
            "required_date": req.required_date, "item": req.item, "total": sel["total"],
            "vendor": {"name": sel["name"], "approved": sel["approved"]},
            "vendors_compared": len([o for o in ctx.get("offers", []) if o["eligible"]]),
            "hr_verified": (hr["status"] == "pass") if hr else None, "price_delta_pct": sel.get("price_delta_pct")}


def _summary(rows: list[dict]) -> dict:
    counts = Counter(r["outcome"] for r in rows)
    return {**{k: counts.get(k, 0) for k in OUTCOMES}, "needs_human": sum(r["needs_human"] for r in rows)}


def simulate(db: Session, org_id: int, changes: list[dict], sample: int = 1000) -> dict:
    stored = db.query(Policy).filter(Policy.org_id == org_id, Policy.function_key == "procurement").order_by(Policy.id).all()
    current = [_copy(p) for p in stored]
    proposed = apply_changes(stored, changes)
    workflows = (db.query(Workflow).filter(Workflow.org_id == org_id, Workflow.function_key == "procurement")
                 .order_by(Workflow.id.desc()).limit(sample).all())
    before, after, changed = [], [], []
    for wf in workflows:
        facts = _facts_from(wf)
        if facts is None:
            continue
        ov = (wf.context or {}).get("overrides", {})
        kwargs = {"accepted_blocks": set(ov.get("accepted_policy_blocks", [])), "anomaly_accepted": bool(ov.get("accept_price_anomaly"))}
        a, b = classify(facts, current, **kwargs), classify(facts, proposed, **kwargs)
        before.append(a)
        after.append(b)
        if a["outcome"] != b["outcome"]:
            changed.append({"workflow_id": wf.id, "ref": f"WF-{1000 + wf.id}", "title": wf.title, "amount": facts["total"],
                            "before": a["outcome"], "after": b["outcome"]})
    cur, new = _summary(before), _summary(after)
    reduction = round((cur["needs_human"] - new["needs_human"]) / cur["needs_human"] * 100, 1) if cur["needs_human"] else None
    return {"sampled": len(workflows), "replayed": len(before), "skipped": len(workflows) - len(before),
            "current": cur, "proposed": new, "human_workload_change_pct": reduction,
            "changed_count": len(changed), "changed": changed[:25],
            "note": "Replays recorded requests against the policy engine; nothing is saved or executed."}


def simulate_one(db: Session, org_id: int, purchase: dict, changes: list[dict]) -> dict:
    stored = db.query(Policy).filter(Policy.org_id == org_id, Policy.function_key == "procurement").order_by(Policy.id).all()
    facts = {"category": purchase["category"], "quantity": purchase["quantity"], "budget": purchase.get("budget"),
             # complete documentation by default so a what-if isolates the rules being changed, not missing fields
             "purpose": purchase.get("purpose") or "Hypothetical purchase", "required_date": date.today() + timedelta(days=14),
             "item": purchase.get("item") or purchase["category"],
             "total": purchase["amount"], "vendor": {"name": "Hypothetical vendor", "approved": purchase.get("vendor_approved", True)},
             "vendors_compared": purchase.get("vendors_compared", 3), "hr_verified": None,
             "price_delta_pct": purchase.get("price_delta_pct")}
    return {"current": classify(facts, [_copy(p) for p in stored]), "proposed": classify(facts, apply_changes(stored, changes))}
