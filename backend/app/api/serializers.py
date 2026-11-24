from sqlalchemy.orm import Session

from app.models import Approval, AuditEvent, Decision, PurchaseOrder, Request, Workflow, WorkflowException, WorkflowStep

DONE = {"completed", "resolved", "skipped"}


def wf_ref(wid: int) -> str:
    return f"WF-{1000 + wid}"


def ser_user(u) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "department": u.department}


def ser_request(r: Request) -> dict:
    return {
        "id": r.id, "source": r.source, "raw_text": r.raw_text, "status": r.status, "item": r.item, "category": r.category,
        "quantity": r.quantity, "purpose": r.purpose, "required_date": r.required_date, "required_date_text": r.required_date_text,
        "budget": r.budget, "currency": r.currency, "requirements": r.requirements, "requester_name": r.requester_name,
        "requester": r.requester.name if r.requester else None, "confidence": r.confidence,
        "extraction_engine": r.extraction_engine, "extraction_notes": r.extraction_notes, "corrected": r.corrected,
        "demo_faults": r.demo_faults, "created_at": r.created_at,
    }


def ser_step(s: WorkflowStep) -> dict:
    return {
        "id": s.id, "key": s.key, "name": s.name, "position": s.position, "kind": s.kind, "status": s.status, "action": s.action,
        "input": s.input, "output": s.output, "decision": s.decision, "reason": s.reason, "error": s.error, "attempts": s.attempts,
        "started_at": s.started_at, "completed_at": s.completed_at,
        "duration_ms": int((s.completed_at - s.started_at).total_seconds() * 1000) if s.completed_at and s.started_at else None,
    }


def ser_workflow(w: Workflow, steps: list[WorkflowStep] | None = None, pending: int = 0) -> dict:
    steps = steps if steps is not None else w.steps
    done = len([s for s in steps if s.status in DONE])
    return {
        "id": w.id, "ref": wf_ref(w.id), "title": w.title, "function_key": w.function_key, "status": w.status,
        "current_step": w.current_step_key, "progress": {"done": done, "total": len(steps)},
        "requester": w.request.requester.name if w.request and w.request.requester else None,
        "amount": (w.context or {}).get("selected", {}).get("total"), "is_demo": w.is_demo, "pending_approvals": pending,
        "created_at": w.created_at, "started_at": w.started_at, "completed_at": w.completed_at, "error": w.error,
        "outcome": w.outcome,
    }


def ser_decision(d: Decision) -> dict:
    return {"id": d.id, "step_id": d.step_id, "kind": d.kind, "level": d.level, "outcome": d.outcome, "reason": d.reason,
            "rule_trace": d.rule_trace, "actor": d.actor, "actor_type": d.actor_type, "created_at": d.created_at}


def ser_exception(e: WorkflowException, wf: Workflow | None = None) -> dict:
    return {
        "id": e.id, "workflow_id": e.workflow_id, "workflow_ref": wf_ref(e.workflow_id), "workflow_title": wf.title if wf else None,
        "step_id": e.step_id, "code": e.code, "category": e.category, "severity": e.severity, "recoverable": e.recoverable,
        "status": e.status, "message": e.message, "details": {k: v for k, v in (e.details or {}).items() if k != "offers"},
        "attempts": e.attempts, "resolution": e.resolution, "resolution_trace": e.resolution_trace, "resolved_by": e.resolved_by,
        "detected_at": e.detected_at, "resolved_at": e.resolved_at,
    }


def ser_approval(a: Approval, wf: Workflow | None = None) -> dict:
    return {
        "id": a.id, "workflow_id": a.workflow_id, "workflow_ref": wf_ref(a.workflow_id), "workflow_title": wf.title if wf else None,
        "requester": wf.request.requester.name if wf and wf.request and wf.request.requester else None,
        "exception_id": a.exception_id, "kind": a.kind, "level": a.level, "title": a.title, "summary": a.summary,
        "reason": a.reason, "recommendation": a.recommendation, "risk": a.risk, "risk_level": a.risk_level,
        "supporting_data": a.supporting_data, "options": a.options, "assigned_role": a.assigned_role, "status": a.status,
        "escalated": a.escalated, "decided_by": a.decided_by, "decided_by_role": a.decided_by_role,
        "decision_note": a.decision_note, "modification": a.modification, "created_at": a.created_at, "decided_at": a.decided_at,
    }


def ser_audit(e: AuditEvent) -> dict:
    return {"id": e.id, "ts": e.ts, "workflow_id": e.workflow_id, "workflow_ref": wf_ref(e.workflow_id) if e.workflow_id else None,
            "actor_type": e.actor_type, "actor": e.actor, "action": e.action, "input": e.input, "output": e.output,
            "result": e.result, "reason": e.reason, "status": e.status, "duration_ms": e.duration_ms}


def ser_po(p: PurchaseOrder) -> dict:
    return {"id": p.id, "po_number": p.po_number, "vendor": p.vendor.name if p.vendor else None, "item": p.item,
            "quantity": p.quantity, "unit_price": p.unit_price, "total": p.total, "currency": p.currency, "status": p.status,
            "erp_ref": p.erp_ref, "accounting_ref": p.accounting_ref, "document_ref": p.document_ref,
            "expected_delivery": p.expected_delivery, "created_at": p.created_at}


def ser_workflow_detail(db: Session, w: Workflow) -> dict:
    steps = db.query(WorkflowStep).filter(WorkflowStep.workflow_id == w.id).order_by(WorkflowStep.position).all()
    approvals = db.query(Approval).filter(Approval.workflow_id == w.id).order_by(Approval.id).all()
    pending = len([a for a in approvals if a.status == "pending"])
    ctx = w.context or {}
    po = db.query(PurchaseOrder).filter(PurchaseOrder.workflow_id == w.id).first()
    audit = db.query(AuditEvent).filter(AuditEvent.workflow_id == w.id, AuditEvent.action.notlike("step.%")).order_by(AuditEvent.id).all()
    return {
        **ser_workflow(w, steps, pending),
        "request": ser_request(w.request) if w.request else None,
        "plan": w.plan,
        "steps": [ser_step(s) for s in steps],
        "decisions": [ser_decision(d) for d in db.query(Decision).filter(Decision.workflow_id == w.id).order_by(Decision.id)],
        "exceptions": [ser_exception(e, w) for e in db.query(WorkflowException).filter(WorkflowException.workflow_id == w.id).order_by(WorkflowException.id)],
        "approvals": [ser_approval(a, w) for a in approvals],
        "audit": [ser_audit(e) for e in audit],
        "purchase_order": ser_po(po) if po else None,
        "outcome_data": w.outcome_data,
        "context": {"overrides": ctx.get("overrides", {}), "grant": ctx.get("grant"), "faults": ctx.get("faults", []),
                    "faults_consumed": ctx.get("faults_consumed", []),
                    "input": ctx.get("input"), "fields": ctx.get("fields"), "definition": ctx.get("definition")},
    }


def page(items: list, total: int, page_no: int, size: int) -> dict:
    return {"items": items, "total": total, "page": page_no, "page_size": size, "pages": max((total + size - 1) // size, 1)}
