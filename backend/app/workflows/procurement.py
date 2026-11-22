"""Procurement: the first business function implemented on the reusable workflow engine.

Nothing here is engine logic — it only declares steps, handlers and exception specs. A future function
(finance ops, onboarding, collections…) defines its own WorkflowDefinition and reuses every engine."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.agents import explain
from app.agents.planner import build_plan
from app.core.db import utcnow
from app.decisions.engine import DecisionConfig, decide
from app.exceptions.engine import ExceptionSpec, ResolverResult, register as register_exception
from app.models import Decision, Policy, PurchaseOrder, WorkflowException
from app.services import policy_engine, vendor_scoring
from app.services.policy_engine import inr
from app.workflows import registry
from app.workflows.types import ApprovalSpec, FlowException, StepContext, StepDef, StepResult, WorkflowDefinition

AGENT_SCOPES = frozenset({
    "documents:write", "crm:read", "hr:read", "vendors:read", "vendors:write",
    "accounting:read", "accounting:write", "erp:write", "email:send",
})  # deliberately excludes payments:release

NON_RULE_CATEGORIES = {"decision", "exception"}


# ---------------------------------------------------------------- helpers
def _policies(db: Session, org_id: int) -> list[Policy]:
    return db.query(Policy).filter(Policy.org_id == org_id, Policy.function_key == "procurement").order_by(Policy.id).all()


def _days_until(req) -> int | None:
    if not req.required_date:
        return None
    return max((req.required_date - utcnow().date()).days, 0)


def _facts(sctx: StepContext, **extra) -> dict:
    r = sctx.request
    base = {"category": r.category, "quantity": r.quantity, "budget": r.budget, "purpose": r.purpose,
            "required_date": r.required_date, "item": r.item}
    base.update(extra)
    return base


def _apply_policy_override(report: policy_engine.PolicyReport, overrides: dict) -> None:
    accepted = set(overrides.get("accepted_policy_blocks", []))
    if not accepted:
        return
    for res in report.results:
        if res.key in accepted and res.status == "fail" and res.severity == "block":
            res.status, res.severity = "warn", "warn"
            res.message += " — overridden by authorised human review"


def _po_for(sctx: StepContext) -> PurchaseOrder | None:
    return sctx.db.query(PurchaseOrder).filter(PurchaseOrder.workflow_id == sctx.workflow.id).first()


# ---------------------------------------------------------------- step handlers
def ingest(sctx: StepContext) -> StepResult:
    r = sctx.request
    doc = sctx.tool("documents.store", name=f"request-{r.id}.txt", content=r.raw_text)
    sctx.audit("request.received", actor_type="user", actor=r.requester.name,
               input={"source": r.source, "text": r.raw_text[:400]}, output={"request_id": r.id, "document": doc["ref"]},
               status="received")
    return StepResult(output={"request_id": r.id, "source": r.source, "document_ref": doc["ref"], "characters": len(r.raw_text)},
                      decision="Accepted for processing", reason=f"Request received via {r.source.replace('_', ' ')} and archived")


def understand(sctx: StepContext) -> StepResult:
    r = sctx.request
    missing = [f for f in ("category", "quantity", "budget") if not getattr(r, f)]
    if missing:
        raise FlowException("MISSING_INFORMATION", f"Request is missing: {', '.join(missing)}")
    stakeholder = sctx.tool("crm.get_stakeholder", name=r.requester_name or r.requester.name, email=r.requester.email)
    extracted = {"item": r.item, "category": r.category, "quantity": r.quantity, "purpose": r.purpose,
                 "required_date": r.required_date, "required_date_text": r.required_date_text, "budget": r.budget,
                 "requirements": r.requirements}
    sctx.audit("request.extracted", actor_type="ai", actor=f"Extraction Agent ({r.extraction_engine})",
               input={"text": r.raw_text[:300]}, output=extracted, reason=f"Confidence {int(r.confidence * 100)}%"
               + (" — corrected by a human before execution" if r.corrected else ""), status="understood")
    sctx.set(stakeholder=stakeholder)
    return StepResult(
        output={"extracted": extracted, "stakeholder": stakeholder, "confidence": r.confidence,
                "engine": r.extraction_engine, "human_corrected": r.corrected, "notes": r.extraction_notes,
                "plan": sctx.workflow.plan},
        decision=f"Understood as {r.quantity}× {r.category}", reason=f"Extraction confidence {int(r.confidence * 100)}% via {r.extraction_engine}")


def policy_check(sctx: StepContext) -> StepResult:
    r = sctx.request
    hr_verified = None
    text = (r.purpose or "").lower()
    if any(k in text for k in ("new employee", "new hire", "joining", "onboard", "joiner")):
        hr = sctx.tool("hr.verify_new_hire", requester=r.requester.name, purpose=r.purpose)
        hr_verified = hr["verified"]
    facts = _facts(sctx, hr_verified=hr_verified)
    report = policy_engine.evaluate(facts, _policies(sctx.db, sctx.workflow.org_id))
    _apply_policy_override(report, sctx.overrides)
    sctx.audit("policy.evaluated", actor="Policy Engine", input=facts, output=report.to_dict(),
               result="pass" if report.passed else "fail", status="validated")
    sctx.set(policy_report=report.to_dict())
    if not report.passed:
        raise FlowException("POLICY_BLOCK", "Policy violation: " + "; ".join(x.message for x in report.blocking),
                            {"results": report.to_dict()["results"], "budget": r.budget})
    warns = len(report.warnings)
    return StepResult(output=report.to_dict(), decision="Policies satisfied" if not warns else f"Policies satisfied with {warns} flag(s)",
                      reason="; ".join(x.message for x in report.approvals_required) or "No approvals mandated at request stage")


def _vendor_input(sctx: StepContext) -> dict:
    r = sctx.request
    return {"category": r.category, "quantity": r.quantity, "budget": r.budget, "days_until_required": _days_until(r),
            "overrides": sctx.overrides, "excluded_vendor_ids": sctx.ctx.get("excluded_vendor_ids", [])}


def vendor_evaluation(sctx: StepContext) -> StepResult:
    r = sctx.request
    ctx, ov = sctx.ctx, sctx.overrides
    vendors = sctx.tool("vendors.search", category=r.category)
    weights = next((p.params.get("weights") for p in _policies(sctx.db, sctx.workflow.org_id)
                    if p.rule_type == "vendor_scoring" and p.enabled), None)
    days = _days_until(r)
    offers = vendor_scoring.evaluate_vendors(
        vendors, category=r.category, quantity=r.quantity, budget=r.budget, days_until_required=days, weights=weights,
        excluded_ids=set(ctx.get("excluded_vendor_ids", [])), relax=bool(ov.get("relax_constraints")))
    eligible = [o for o in offers if o["eligible"]]
    if not eligible:
        sctx.set(offers=offers)
        raise FlowException("NO_ELIGIBLE_VENDOR", "No approved vendor can meet the budget and delivery requirements",
                            {"offers": offers, "days": days, "budget": r.budget})
    forced = ov.get("forced_vendor_id")
    if forced is None:
        selected = eligible[0]
    else:
        selected = next((o for o in eligible if o["vendor_id"] == forced), None)
        if selected is None:
            # A reviewer chose this vendor. Never quietly substitute another one: surface it and ask a human.
            chosen = next((o for o in offers if o["vendor_id"] == forced), None)
            why = "; ".join(chosen["reasons"]) if chosen and chosen["reasons"] else "it is not among the evaluated vendors"
            name = chosen["name"] if chosen else f"vendor #{forced}"
            raise FlowException("FORCED_VENDOR_INELIGIBLE", f"The vendor chosen by a reviewer ({name}) is not eligible: {why}",
                                {"vendor_id": forced, "vendor": name, "offers": offers, "days": days, "budget": r.budget})
    recommendation = explain.vendor_recommendation(offers, selected, days)
    cfg = DecisionConfig.from_policies(_policies(sctx.db, sctx.workflow.org_id))
    sctx.set(offers=offers, selected=selected, recommendation=recommendation)
    sctx.audit("vendors.evaluated", actor_type="ai", actor="Vendor Evaluation Agent",
               input={"category": r.category, "quantity": r.quantity, "days_until_required": days},
               output={"selected": selected["name"], "ranking": [(o["name"], o["score"]) for o in eligible]},
               reason=recommendation, status="recommended")
    delta = selected["price_delta_pct"]
    if delta is not None and delta > cfg.anomaly_pct and not ov.get("accept_price_anomaly"):
        raise FlowException("PRICE_ANOMALY", f"{selected['name']}'s price is {delta}% above its historical average",
                            {"vendor_id": selected["vendor_id"], "vendor": selected["name"], "unit_price": selected["unit_price"],
                             "quantity": r.quantity, "historical_avg": selected["historical_avg"], "delta": delta,
                             "threshold": cfg.anomaly_pct, "offers": offers, "days": days, "budget": r.budget})
    sctx.db.add(Decision(workflow_id=sctx.workflow.id, step_id=sctx.step.id, kind="vendor_selection", outcome=selected["name"],
                         reason=recommendation, rule_trace=[{"vendor": o["name"], "score": o["score"], "eligible": o["eligible"],
                                                              "reasons": o["reasons"]} for o in offers],
                         actor="Vendor Evaluation Agent", actor_type="ai"))
    return StepResult(
        output={"offers": offers, "selected": selected, "recommendation": recommendation, "days_until_required": days,
                "weights": weights or vendor_scoring.DEFAULT_WEIGHTS},
        decision=f"Recommended {selected['name']} at {inr(selected['total'])}", reason=recommendation)


def decision_step(sctx: StepContext) -> StepResult:
    r, ctx, ov = sctx.request, sctx.ctx, sctx.overrides
    sel = ctx["selected"]
    policies = _policies(sctx.db, sctx.workflow.org_id)
    facts = _facts(sctx, hr_verified=None, total=sel["total"], vendor={"name": sel["name"], "approved": sel["approved"]},
                   vendors_compared=len([o for o in ctx.get("offers", []) if o["eligible"]]))
    # HR verification was settled in the policy step; carry its result forward
    hr = next((x for x in ctx.get("policy_report", {}).get("results", []) if x["key"] == "hr_new_hire"), None)
    if hr is not None:
        facts["hr_verified"] = hr["status"] == "pass"
    report = policy_engine.evaluate(facts, policies)
    _apply_policy_override(report, ov)
    cfg = DecisionConfig.from_policies(policies)
    result = decide({"amount": sel["total"], "budget": r.budget, "vendor_approved": sel["approved"],
                     "price_delta_pct": sel["price_delta_pct"], "anomaly_accepted": bool(ov.get("accept_price_anomaly")),
                     "grant": ctx.get("grant")}, report, cfg)
    label = f"Level {result.level} — {result.outcome.replace('_', ' ')}"
    sctx.db.add(Decision(workflow_id=sctx.workflow.id, step_id=sctx.step.id, kind="autonomy", level=result.level,
                         outcome=result.outcome, reason="; ".join(result.reasons), rule_trace=result.trace,
                         actor="FlowForge Decision Engine"))
    sctx.audit("decision.made", actor="Decision Engine", input={"amount": sel["total"], "vendor": sel["name"]},
               output=result.to_dict(), reason="; ".join(result.reasons), status=result.outcome)
    sctx.set(decision=result.to_dict(), policy_report_final=report.to_dict())
    return StepResult(output={**result.to_dict(), "policy": report.to_dict()}, decision=label, reason="; ".join(result.reasons))


def approval_step(sctx: StepContext) -> StepResult:
    ctx, r = sctx.ctx, sctx.request
    d, sel = ctx["decision"], ctx["selected"]
    if d["level"] == 1:
        return StepResult(status="skipped", decision="Not required", reason="Level 1 — decision rules allow autonomous execution")
    if d["approval_covered"]:
        g = ctx["grant"]
        return StepResult(status="skipped", decision="Covered by existing approval",
                          reason=f"Approval already granted by {g['by']} ({g['role']}) covers {inr(sel['total'])}")
    level = d["level"]
    report = ctx.get("policy_report_final", {})
    spec = ApprovalSpec(
        title=f"{'Human decision' if level == 3 else 'Approval'} required: {r.quantity}× {r.item or r.category} — {inr(sel['total'])}",
        summary=(f"Procure {r.quantity}× {r.item or r.category} from {sel['name']} for {inr(sel['total'])} "
                 f"({r.purpose or 'purpose not stated'}; needed {r.required_date_text or r.required_date or 'unspecified'})."),
        reason=" ".join(d["reasons"]),
        recommendation=f"Approve. {ctx.get('recommendation', '')}" if sel["total"] <= (r.budget or 0) else
        f"Review carefully: order value {inr(sel['total'])} exceeds the budget of {inr(r.budget)}.",
        risk=("High — significant spend requiring accountable sign-off." if level == 3 else
              "Low — price within budget and vendor approved; approval is required by policy thresholds."),
        risk_level="high" if level == 3 else "low",
        supporting_data={"selected": sel, "offers": ctx.get("offers", []), "policy": report, "budget": r.budget,
                         "decision_trace": d["trace"], "vendor_options": [o for o in ctx.get("offers", []) if o["eligible"] and o["approved"]]},
        assigned_role=d["required_role"] or "approver", level=level)
    return StepResult(status="wait_human", approval=spec, output={"requested_role": spec.assigned_role, "level": level},
                      decision=f"Waiting for {spec.assigned_role}", reason=spec.reason)


def purchase_order(sctx: StepContext) -> StepResult:
    r, ctx = sctx.request, sctx.ctx
    sel = ctx["selected"]
    avail = sctx.tool("vendors.confirm_availability", vendor_id=sel["vendor_id"])
    if not avail["available"]:
        raise FlowException("VENDOR_UNAVAILABLE", f"{sel['name']} cannot fulfil the order ({avail['stock']})",
                            {"vendor_id": sel["vendor_id"], "vendor": sel["name"], "offers": ctx.get("offers", []),
                             "days": _days_until(r), "budget": r.budget})
    cost_center = (ctx.get("stakeholder") or {}).get("cost_center", "CC-GENERAL")
    budget = sctx.tool("accounting.check_budget", amount=sel["total"], cost_center=cost_center)
    if not budget["available"]:
        raise FlowException("BUDGET_UNAVAILABLE", f"Cost centre {cost_center} lacks budget for {inr(sel['total'])}")
    po = _po_for(sctx)
    if po is None:
        po = PurchaseOrder(workflow_id=sctx.workflow.id, vendor_id=sel["vendor_id"], po_number=f"PO-{utcnow().year}-{sctx.workflow.id:05d}",
                           item=r.item or r.category, quantity=r.quantity, unit_price=sel["unit_price"], total=sel["total"],
                           currency=r.currency, status="draft")
        sctx.db.add(po)
    po.vendor_id, po.unit_price, po.total = sel["vendor_id"], sel["unit_price"], sel["total"]
    doc = sctx.tool("documents.store", name=f"{po.po_number}.pdf", content=f"{po.po_number}|{po.item}|{po.quantity}|{po.total}")
    po.document_ref, po.status = doc["ref"], "issued"
    sctx.db.flush()
    sctx.tool("email.send", to=f"orders@{sel['name'].lower().replace(' ', '')}.example", subject=f"Purchase order {po.po_number}",
              body=f"Please supply {po.quantity}× {po.item} at {inr(po.unit_price)} each.")
    sctx.set(po_number=po.po_number)
    return StepResult(output={"po_number": po.po_number, "vendor": sel["name"], "total": po.total, "document": doc["ref"],
                              "budget_check": budget}, decision=f"Issued {po.po_number}",
                      reason=f"{sel['name']} confirmed availability; {cost_center} has budget")


def erp_update(sctx: StepContext) -> StepResult:
    po = _po_for(sctx)
    erp = sctx.tool("erp.create_purchase_order", po={"po_number": po.po_number, "vendor_id": po.vendor_id, "total": po.total})
    acc = sctx.tool("accounting.reserve_commitment", po_number=po.po_number, amount=po.total)
    po.erp_ref, po.accounting_ref = erp["erp_ref"], acc["accounting_ref"]
    return StepResult(output={"erp": erp, "accounting": acc}, decision="ERP and accounting updated",
                      reason=f"PO posted as {erp['erp_ref']}; commitment {acc['accounting_ref']}")


def fulfillment(sctx: StepContext) -> StepResult:
    po, r = _po_for(sctx), sctx.request
    conf = sctx.tool("vendors.confirm_order", po_number=po.po_number, vendor_id=po.vendor_id)
    po.status = "confirmed"
    po.expected_delivery = date.fromisoformat(conf["eta_date"])
    sctx.tool("email.send", to=r.requester.email, subject=f"Order confirmed: {po.item}",
              body=f"{po.po_number} confirmed. Expected delivery {po.expected_delivery}.")
    return StepResult(output={"vendor_confirmation": conf, "expected_delivery": po.expected_delivery, "requester_notified": r.requester.email},
                      decision="Vendor confirmed order", reason=f"ETA {po.expected_delivery} (tracking {conf['tracking']})")


def verification(sctx: StepContext) -> StepResult:
    po, r, ctx, ov = _po_for(sctx), sctx.request, sctx.ctx, sctx.overrides
    checks = []

    def check(name, ok, detail, hard=True):
        checks.append({"check": name, "ok": ok, "detail": detail, "hard": hard})

    check("ERP reference recorded", bool(po.erp_ref), po.erp_ref or "missing")
    check("Accounting commitment recorded", bool(po.accounting_ref), po.accounting_ref or "missing")
    covered = bool(ctx.get("grant")) and po.total <= ctx["grant"]["max_amount"]
    check("Spend within budget or explicitly approved", po.total <= (r.budget or 0) or covered,
          f"{inr(po.total)} vs budget {inr(r.budget)}")
    if r.required_date and po.expected_delivery:
        late = po.expected_delivery > r.required_date
        check("Delivery meets required date", not late or bool(ov.get("relax_constraints")),
              f"ETA {po.expected_delivery} vs required {r.required_date}")
    match = sctx.tool("accounting.match_invoice", po_number=po.po_number, amount=po.total)
    check("Invoice matches purchase order (3-way match)", match["matched"],
          f"invoice {inr(match['invoice_total'])} vs PO {inr(match['po_total'])}")
    failed = [c for c in checks if not c["ok"] and c["hard"]]
    if failed:
        raise FlowException("VERIFICATION_MISMATCH", "Verification failed: " + "; ".join(f"{c['check']} ({c['detail']})" for c in failed),
                            {"checks": checks}, recoverable=False)
    return StepResult(output={"checks": checks, "invoice": match}, decision="Verified",
                      reason=f"{len(checks)} checks passed, invoice matched PO")


def complete(sctx: StepContext) -> StepResult:
    wf, r, db = sctx.workflow, sctx.request, sctx.db
    po = _po_for(sctx)
    excs = db.query(WorkflowException).filter(WorkflowException.workflow_id == wf.id).all()
    from app.models import Approval

    humans = db.query(Approval).filter(Approval.workflow_id == wf.id, Approval.status.in_(["approved", "modified"])).count()
    auto = len([e for e in excs if e.status in ("auto_resolved", "retrying", "resolving")])
    outcome = explain.final_outcome(
        {"po_number": po.po_number, "quantity": po.quantity, "item": po.item, "total": po.total, "erp_ref": po.erp_ref,
         "accounting_ref": po.accounting_ref, "expected_delivery": po.expected_delivery}, po.vendor.name, humans, len(excs), auto)
    wf.outcome = outcome
    wf.outcome_data = {"po_number": po.po_number, "vendor": po.vendor.name, "total": po.total, "erp_ref": po.erp_ref,
                       "accounting_ref": po.accounting_ref, "expected_delivery": str(po.expected_delivery),
                       "human_decisions": humans, "exceptions": len(excs), "auto_resolved": auto}
    r.status = "closed"
    sctx.tool("email.send", to=r.requester.email, subject=f"Procurement complete: {po.po_number}", body=outcome)
    return StepResult(output=wf.outcome_data, decision="Procurement complete", reason=outcome)


def completion_criteria(db: Session, wf) -> list[str]:
    unmet = []
    po = db.query(PurchaseOrder).filter(PurchaseOrder.workflow_id == wf.id).first()
    if po is None:
        return ["no purchase order exists"]
    if not po.erp_ref:
        unmet.append("ERP reference missing")
    if not po.accounting_ref:
        unmet.append("accounting commitment missing")
    open_exc = db.query(WorkflowException).filter(
        WorkflowException.workflow_id == wf.id,
        WorkflowException.status.in_(["open", "awaiting_review", "escalated", "failed", "retrying", "resolving"])).count()
    # statuses retrying/resolving are closed out when their step completes, so any left over are unresolved
    if open_exc:
        unmet.append(f"{open_exc} unresolved exception(s)")
    return unmet


# ---------------------------------------------------------------- exception specs
def alternative_vendor_resolver(sctx: StepContext, fe: FlowException) -> ResolverResult:
    """Search approved alternatives → recalculate price → (engine) re-run policy check and decision."""
    ctx, ov = sctx.ctx, sctx.overrides
    d = fe.details
    cfg = DecisionConfig.from_policies(_policies(sctx.db, sctx.workflow.org_id))
    current = d.get("vendor_id")
    excluded = set(ctx.get("excluded_vendor_ids", []))
    if fe.code == "VENDOR_UNAVAILABLE":
        excluded.add(current)
    rejected, candidates = [], []
    for o in d.get("offers") or ctx.get("offers", []):
        if o["vendor_id"] == current:
            continue
        why = list(o["reasons"])
        if o["vendor_id"] in excluded and "Currently unavailable" not in why:
            why.append("Currently unavailable")
        if o["price_delta_pct"] is not None and o["price_delta_pct"] > cfg.anomaly_pct:
            why.append(f"price is {o['price_delta_pct']}% above its historical average")
        if fe.code == "PRICE_ANOMALY" and o["reliability"] < cfg.min_alt_reliability:
            why.append(f"reliability {o['reliability']:g}% is below the required {cfg.min_alt_reliability:g}%")
        (rejected if why else candidates).append({"vendor": o["name"], "why": why, "offer": o} if why else o)
    fe.details = {**fe.details, "alternatives_rejected": [{"vendor": r["vendor"], "why": r["why"]} for r in rejected]}
    if not candidates:
        names = "; ".join(f"{r['vendor']}: {', '.join(r['why'])}" for r in rejected) or "no other approved vendors"
        return ResolverResult(False, f"Searched approved alternatives — none safe to substitute ({names})")
    best = max(candidates, key=lambda o: o["score"])
    return ResolverResult(
        True, f"Approved alternative {best['name']} found at {inr(best['total'])}; recalculating price, re-running policy checks and decision",
        patch={"overrides": {**ov, "forced_vendor_id": best["vendor_id"]}, "excluded_vendor_ids": sorted(excluded)},
        rewind_to="vendor_evaluation", data={"alternative": best["name"]})


def _anomaly_review(sctx: StepContext, fe: FlowException, trace: list[dict]) -> ApprovalSpec:
    d = fe.details
    r = sctx.request
    text = explain.anomaly_review(d, d.get("alternatives_rejected", []), r.budget, d.get("days"))
    rationale = explain.ai_rationale({"summary": text["summary"], "reason": text["reason"], "budget": r.budget})
    eligible = [o for o in d["offers"] if o["eligible"] and o["approved"]]
    return ApprovalSpec(
        title=f"Price anomaly: {d['vendor']} is {d['delta']}% above historical average", summary=text["summary"],
        reason=text["reason"], recommendation=text["recommendation"], risk=text["risk"], risk_level="medium",
        supporting_data={"offers": d["offers"], "vendor_options": eligible, "trace": trace, "ai_rationale": rationale,
                         "alternatives_rejected": d.get("alternatives_rejected", []), "budget": r.budget,
                         "price": {"unit": d["unit_price"], "historical": d["historical_avg"], "delta_pct": d["delta"]}},
        assigned_role="approver", level=2, kind="exception_review")


def _no_vendor_review(sctx, fe, trace) -> ApprovalSpec:
    d = fe.details
    why = "; ".join(f"{o['name']}: {', '.join(o['reasons'])}" for o in d["offers"])
    return ApprovalSpec(
        title="No eligible vendor meets the requirements", summary=fe.message,
        reason=f"Every vendor was excluded — {why}.",
        recommendation="Approve to relax delivery/budget constraints and take the best approved vendor, or Reject to stop and re-scope the request.",
        risk="Medium — the order may arrive after the required date or exceed budget.", risk_level="medium",
        supporting_data={"offers": d["offers"], "trace": trace, "vendor_options": [o for o in d["offers"] if o["approved"]]},
        assigned_role="manager", level=2, kind="exception_review", options=["approve", "reject", "escalate"])


def _policy_review(sctx, fe, trace) -> ApprovalSpec:
    return ApprovalSpec(
        title=f"Policy violation: {sctx.workflow.title}", summary=fe.message,
        reason="A blocking policy failed. Only an accountable administrator can authorise an exception to policy.",
        recommendation="Reject unless there is a documented business justification; policy exceptions are audited.",
        risk="High — proceeding bypasses an organisational control.", risk_level="high",
        supporting_data={"policy": fe.details.get("results", []), "trace": trace},
        assigned_role="admin", level=3, kind="exception_review", options=["approve", "reject"])


def _validate_vendor_swap(details: dict, modification: dict) -> str | None:
    """A reviewer may only swap in a vendor the engine evaluated and considers approved and eligible."""
    vendor_id = modification.get("vendor_id")
    offer = next((o for o in details.get("offers") or [] if o["vendor_id"] == vendor_id), None)
    if offer is None:
        return "The chosen vendor was not evaluated for this request."
    if not offer["approved"]:
        return f"{offer['name']} is not an approved vendor."
    if not offer["eligible"]:
        return f"{offer['name']} is not eligible for this request ({'; '.join(offer['reasons']) or 'constraints not met'})."
    return None


def _validate_unavailable_swap(details: dict, modification: dict) -> str | None:
    if modification.get("vendor_id") == details.get("vendor_id"):
        return f"{details.get('vendor', 'That vendor')} is the vendor that is unavailable; choose a different one."
    return _validate_vendor_swap(details, modification)


register_exception(ExceptionSpec(
    "PRICE_ANOMALY", "vendor", "Vendor price anomaly", severity="medium", resolvers=[alternative_vendor_resolver],
    review_builder=_anomaly_review, review_role="approver",
    on_approve=lambda d: {"accept_price_anomaly": True, "forced_vendor_id": d["vendor_id"]},
    on_modify=lambda d, m: {"forced_vendor_id": int(m["vendor_id"]), "accept_price_anomaly": True},
    validate_modify=_validate_vendor_swap))
register_exception(ExceptionSpec(
    "VENDOR_UNAVAILABLE", "vendor", "Vendor unavailable", severity="medium", resolvers=[alternative_vendor_resolver],
    review_role="manager", on_approve=lambda d: {}, on_modify=lambda d, m: {"forced_vendor_id": int(m["vendor_id"])},
    validate_modify=_validate_unavailable_swap))
register_exception(ExceptionSpec(
    # Approving acknowledges the problem and lets the engine rank vendors normally again (price-anomaly rules still apply).
    "FORCED_VENDOR_INELIGIBLE", "vendor", "Chosen vendor is no longer eligible", severity="medium", review_role="approver",
    on_approve=lambda d: {"forced_vendor_id": None, "accept_price_anomaly": False}))
register_exception(ExceptionSpec(
    "NO_ELIGIBLE_VENDOR", "vendor", "No eligible vendor", severity="high", review_builder=_no_vendor_review,
    review_role="manager", on_approve=lambda d: {"relax_constraints": True}))
def _approve_policy_block(details: dict) -> dict:
    # A human may override only the specific blocking rules that were presented for review.
    # Never grant a blanket policy bypass or an artificial unlimited spend ceiling.
    accepted = [r["key"] for r in details.get("results", []) if r.get("status") == "fail" and r.get("severity") == "block"]
    return {"accepted_policy_blocks": accepted}


register_exception(ExceptionSpec(
    "POLICY_BLOCK", "policy", "Policy violation", severity="high", review_builder=_policy_review, review_role="admin",
    on_approve=_approve_policy_block))
register_exception(ExceptionSpec(
    "BUDGET_UNAVAILABLE", "policy", "Cost-centre budget unavailable", severity="high", review_role="manager",
    on_approve=lambda d: {}))
register_exception(ExceptionSpec(
    "VERIFICATION_MISMATCH", "verification", "Verification mismatch", severity="high", recoverable=False, human_review=False))
register_exception(ExceptionSpec(
    "MISSING_INFORMATION", "data", "Missing information", severity="low", recoverable=False, human_review=False))


# ---------------------------------------------------------------- definition
DEFINITION = registry.register(WorkflowDefinition(
    key="procurement.standard", function_key="procurement", name="Procurement", agent_scopes=AGENT_SCOPES,
    completion_criteria=completion_criteria, plan_fn=build_plan,
    steps=[
        StepDef("ingest", "Request", ingest, action="Register the request and archive the original input",
                allowed_tools=("documents.store",)),
        StepDef("understand", "Understand", understand, action="Validate AI-extracted data and enrich from CRM",
                allowed_tools=("crm.get_stakeholder",)),
        StepDef("policy_check", "Policy Check", policy_check, kind="decision",
                action="Evaluate configured business policies", allowed_tools=("hr.verify_new_hire",)),
        StepDef("vendor_evaluation", "Vendor Evaluation", vendor_evaluation, kind="decision", input_fn=_vendor_input,
                action="Compare approved vendors and recommend one", allowed_tools=("vendors.search",)),
        StepDef("decision", "Decision", decision_step, kind="decision",
                action="Apply decision rules: auto-execute, review or human decision"),
        StepDef("approval", "Approval", approval_step, kind="approval", action="Human approval when decision rules require it"),
        StepDef("purchase_order", "Purchase Order", purchase_order, action="Confirm availability, check budget, issue the PO",
                allowed_tools=("vendors.confirm_availability", "accounting.check_budget", "documents.store", "email.send")),
        StepDef("erp_update", "ERP Update", erp_update, action="Post the PO to ERP and commit spend in accounting",
                allowed_tools=("erp.create_purchase_order", "accounting.reserve_commitment")),
        StepDef("fulfillment", "Fulfillment", fulfillment, action="Confirm with the vendor and notify the requester",
                allowed_tools=("vendors.confirm_order", "email.send")),
        StepDef("verification", "Verification", verification, action="Verify references, budget, delivery and invoice match",
                allowed_tools=("accounting.match_invoice",)),
        StepDef("complete", "Complete", complete, action="Close the request and record the outcome",
                allowed_tools=("email.send",)),
    ]))
