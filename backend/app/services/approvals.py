"""Human-in-the-loop: opening approvals and applying human decisions, then resuming the workflow."""
from __future__ import annotations

from app.core.db import utcnow
from app.core.security import ROLE_RANK, has_permission, role_at_least
from app.exceptions import engine as exception_engine
from app.models import Approval, Decision, Vendor, Workflow, WorkflowException, WorkflowStep
from app.services import audit as audit_service
from app.workflows import engine as wf_engine
from app.workflows.types import ApprovalSpec

ROLE_LADDER = ["approver", "manager", "admin"]


class ApprovalError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def open_approval(sctx, spec: ApprovalSpec, exception: WorkflowException | None = None) -> Approval:
    db, wf, step = sctx.db, sctx.workflow, sctx.step
    approval = Approval(
        workflow_id=wf.id, step_id=step.id, exception_id=exception.id if exception else None, kind=spec.kind,
        level=spec.level, title=spec.title, summary=spec.summary, reason=spec.reason,
        recommendation=spec.recommendation, risk=spec.risk, risk_level=spec.risk_level,
        supporting_data=audit_service.json_safe(spec.supporting_data), options=spec.options,
        assigned_role=spec.assigned_role, status="pending",
    )
    db.add(approval)
    step.status = "waiting_human"
    wf.status = "waiting_human"
    db.flush()
    sctx.audit("approval.requested", actor_type="ai", actor="FlowForge",
               input={"step": step.key, "kind": spec.kind, "level": spec.level},
               output={"approval_id": approval.id, "assigned_role": spec.assigned_role},
               reason=spec.reason, status="pending")
    db.commit()
    return approval


def can_decide(user, approval: Approval, workflow: Workflow) -> str | None:
    if workflow.org_id != user.org_id:  # defence in depth: the API already hides other organisations' approvals
        return "This approval belongs to another organisation."
    if not has_permission(user.role, "approvals:decide"):
        return f"Your role ({user.role}) cannot decide approvals."
    if not role_at_least(user.role, approval.assigned_role):
        return f"This decision requires the '{approval.assigned_role}' role or higher."
    req = workflow.request
    # Applies to every role, administrators included: nobody approves their own purchase.
    if req is not None and req.requester_id == user.id:
        return "Separation of duties: you cannot decide on your own request."
    return None


def _validate_modification(db, approval: Approval, wf: Workflow, exc: WorkflowException | None, ctx: dict,
                           modification: dict | None):
    """Check a 'modify' decision. Returns (vendor, unit_price) for an approval-step modification, else None."""
    vendor_id = (modification or {}).get("vendor_id")
    if isinstance(vendor_id, bool) or not isinstance(vendor_id, int) or vendor_id < 1:
        raise ApprovalError("Modify requires a modification with a positive integer 'vendor_id'.", 422)

    if approval.kind == "exception_review":
        spec = exception_engine.spec_for(exc.code) if exc else None
        if spec is None or spec.on_modify is None:
            raise ApprovalError("This exception cannot be resolved by modifying it.", 422)
        problem = spec.validate_modify(exc.details or {}, modification) if spec.validate_modify else None
        if problem:
            raise ApprovalError(problem, 422)
        return None

    vendor = db.get(Vendor, vendor_id)
    if vendor is None or vendor.org_id != wf.org_id or not vendor.approved:
        raise ApprovalError("The chosen vendor does not exist or is not approved.", 422)
    category = wf.request.category if wf.request else None
    unit = (vendor.catalog or {}).get(category)
    if unit is None:
        raise ApprovalError("That vendor does not supply this category.", 422)
    offers = ctx.get("offers") or []
    if offers:  # the vendors the engine actually evaluated; the engine will refuse anything it considers ineligible
        offer = next((o for o in offers if o["vendor_id"] == vendor.id), None)
        if offer is None or not offer["eligible"]:
            why = "; ".join(offer["reasons"]) if offer and offer["reasons"] else "it was not evaluated for this request"
            raise ApprovalError(f"The chosen vendor is not eligible for this order ({why}).", 422)
    return vendor, unit


def decide(db, approval: Approval, user, action: str, note: str | None, modification: dict | None) -> bool:
    """Apply a human decision. Returns True when the workflow should be resumed."""
    wf = db.get(Workflow, approval.workflow_id)
    if approval.status != "pending":
        raise ApprovalError("This approval has already been decided.", 409)
    if action not in approval.options:
        raise ApprovalError(f"Action '{action}' is not available for this approval.", 422)
    problem = can_decide(user, approval, wf)
    if problem:
        raise ApprovalError(problem, 403)
    if approval.level == 3 and action in ("approve", "reject", "modify") and not (note and note.strip()):
        raise ApprovalError("A written justification is required for Level 3 human decisions.", 422)
    step = db.get(WorkflowStep, approval.step_id)
    exc = db.get(WorkflowException, approval.exception_id) if approval.exception_id else None
    now = utcnow()
    ctx = dict(wf.context or {})
    # Validate a 'modify' up front, before anything is changed: it must either be applied as chosen or refused.
    chosen = _validate_modification(db, approval, wf, exc, ctx, modification) if action == "modify" else None

    def log_decision(outcome: str):
        db.add(Decision(workflow_id=wf.id, step_id=step.id if step else None, kind="human_decision" if approval.kind == "approval" else "exception_resolution",
                        level=approval.level, outcome=outcome,
                        reason=note or f"{outcome.capitalize()} by {user.name}",
                        rule_trace=[{"approval_id": approval.id, "assigned_role": approval.assigned_role, "decided_role": user.role}],
                        actor=user.name, actor_type="user"))
        audit_service.record(db, org_id=wf.org_id, workflow_id=wf.id, actor_type="user", actor=user.name,
                             action="approval.decided", input={"approval_id": approval.id, "action": action, "modification": modification},
                             output={"outcome": outcome}, result=outcome, reason=note, status=outcome)

    if action == "escalate":
        idx = ROLE_LADDER.index(approval.assigned_role) if approval.assigned_role in ROLE_LADDER else 0
        if idx >= len(ROLE_LADDER) - 1:
            raise ApprovalError("Already assigned to the highest authority; it cannot be escalated further.", 422)
        approval.assigned_role = ROLE_LADDER[idx + 1]
        approval.escalated = True
        approval.level = max(approval.level, 3) if approval.assigned_role == "admin" else approval.level
        if exc:
            exc.status = "escalated"
        audit_service.record(db, org_id=wf.org_id, workflow_id=wf.id, actor_type="user", actor=user.name,
                             action="approval.escalated", input={"approval_id": approval.id},
                             output={"assigned_role": approval.assigned_role}, reason=note, status="escalated")
        db.commit()
        return False

    approval.decided_by = user.name
    approval.decided_by_role = user.role
    approval.decision_note = note
    approval.decided_at = now
    approval.modification = modification

    if action == "reject":
        approval.status = "rejected"
        if exc:
            exc.status = "rejected"
            exc.resolved_by = user.name
            exc.resolved_at = now
            exc.resolution = f"Rejected by {user.name}: {note or 'no reason given'}"
        log_decision("rejected")
        db.flush()
        wf_engine.cancel(db, wf, user.name, f"Rejected by {user.name} ({user.role}): {note or 'no reason given'}")
        return False

    approval.status = "modified" if action == "modify" else "approved"
    overrides = dict(ctx.get("overrides", {}))

    if approval.kind == "exception_review":
        spec = exception_engine.spec_for(exc.code) if exc else None
        patch: dict = {}
        if action == "approve" and spec and spec.on_approve:
            patch = spec.on_approve(exc.details or {})
        if action == "modify" and spec and spec.on_modify:
            patch = spec.on_modify(exc.details or {}, modification or {})
        grant = patch.pop("grant", None)
        overrides.update(patch)
        new_ctx = {**ctx, "overrides": overrides}
        if grant:
            new_ctx["grant"] = {**grant, "role": user.role, "by": user.name}
        wf.context = audit_service.json_safe(new_ctx)
        if exc:
            exc.status = "resolved_by_human"
            exc.resolved_by = user.name
            exc.resolved_at = now
            exc.resolution = f"{'Modified' if action == 'modify' else 'Approved'} by {user.name} ({user.role}): {note or 'no note'}"
        step.status = "pending"
        log_decision("modified" if action == "modify" else "approved")
        wf.status = "running"
        db.commit()
        return True

    # approval step
    sel = ctx.get("selected") or {}
    if action == "modify":
        vendor, unit = chosen
        qty = wf.request.quantity or 1
        overrides.update({"forced_vendor_id": vendor.id, "accept_price_anomaly": True})
        wf.context = audit_service.json_safe({**ctx, "overrides": overrides,
                                              "grant": {"role": user.role, "by": user.name, "max_amount": unit * qty, "vendor_id": vendor.id}})
        log_decision("modified")
        wf_engine.rewind(db, wf, "vendor_evaluation")
        wf.status = "running"
        db.commit()
        return True
    wf.context = audit_service.json_safe({**ctx, "grant": {"role": user.role, "by": user.name, "max_amount": sel.get("total", 0),
                                                           "vendor_id": sel.get("vendor_id")}})
    step.status = "completed"
    step.completed_at = now
    step.decision = f"Approved by {user.name} ({user.role})"
    step.reason = note
    step.output = {**(step.output or {}), "approved_by": user.name, "role": user.role, "note": note,
                   "approval_id": approval.id, "decided_at": now.isoformat()}
    log_decision("approved")
    wf.status = "running"
    db.commit()
    return True
