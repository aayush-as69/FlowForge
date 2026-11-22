"""Reusable workflow engine.

A workflow = ordered steps with state, conditions (skips), actions (handlers), exceptions, approvals and
completion criteria. State is persisted after every transition, so a workflow can be resumed after
an interruption (see runner.resume_interrupted)."""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.exceptions import engine as exception_engine
from app.models import Approval, Workflow, WorkflowException, WorkflowStep
from app.services import audit as audit_service
from app.workflows import registry
from app.workflows.types import FlowException, StepContext, StepResult, WorkflowDefinition

DONE = {"completed", "resolved", "skipped"}


def create_workflow(db: Session, definition: WorkflowDefinition, *, org_id: int, title: str, request=None,
                    created_by: int | None = None, context: dict | None = None, is_demo: bool = False,
                    step_delay: float | None = None) -> Workflow:
    wf = Workflow(
        org_id=org_id, function_key=definition.function_key, definition_key=definition.key,
        request_id=request.id if request else None, created_by=created_by, title=title, status="pending",
        context=audit_service.json_safe(context or {}), is_demo=is_demo, step_delay=step_delay,
    )
    db.add(wf)
    db.flush()
    for i, s in enumerate(definition.steps):
        db.add(WorkflowStep(workflow_id=wf.id, key=s.key, name=s.name, position=i, kind=s.kind, action=s.action))
    db.flush()
    if definition.plan_fn:
        wf.plan = audit_service.json_safe(definition.plan_fn(wf))
    db.commit()
    return wf


def steps_of(db: Session, wf: Workflow) -> list[WorkflowStep]:
    return db.query(WorkflowStep).filter(WorkflowStep.workflow_id == wf.id).order_by(WorkflowStep.position).all()


def next_step(db: Session, wf: Workflow) -> WorkflowStep | None:
    for s in steps_of(db, wf):
        if s.status not in DONE:
            return s
    return None


def rewind(db: Session, wf: Workflow, key: str) -> None:
    steps = steps_of(db, wf)
    pos = next(s.position for s in steps if s.key == key)
    for s in steps:
        if s.position >= pos and s.status != "pending":
            s.status = "pending"
            s.completed_at = None
            s.error = None
    audit_service.record(db, org_id=wf.org_id, workflow_id=wf.id, actor_type="system", actor="FlowForge Engine",
                         action="workflow.rewound", input={"to_step": key}, reason="Re-planning after resolution")
    db.commit()


def run(db: Session, workflow_id: int) -> Workflow | None:
    wf = db.get(Workflow, workflow_id)
    if wf is None or wf.status in ("completed", "cancelled"):
        return wf
    definition = registry.get(wf.definition_key)
    resumed = wf.started_at is not None
    if not resumed:
        wf.started_at = utcnow()
    wf.status = "running"
    wf.error = None
    audit_service.record(db, org_id=wf.org_id, workflow_id=wf.id, actor_type="system", actor="FlowForge Engine",
                         action="workflow.resumed" if resumed else "workflow.started",
                         output={"definition": definition.key})
    db.commit()
    delay = wf.step_delay if wf.step_delay is not None else settings.step_delay

    for _ in range(200):  # hard cap protects against runaway rewinds
        db.refresh(wf)
        if wf.status == "cancelled":
            return wf
        step = next_step(db, wf)
        if step is None:
            _finish(db, wf, definition)
            return wf
        wf.current_step_key = step.key
        if step.status == "waiting_human":
            wf.status = "waiting_human"
            db.commit()
            return wf
        if step.status == "failed":
            wf.status = "failed"
            db.commit()
            return wf
        if _execute(db, wf, definition, step) == "stop":
            return wf
        if delay:
            time.sleep(delay)
    wf.status = "failed"
    wf.error = "Workflow exceeded the maximum number of step executions (possible loop)."
    db.commit()
    return wf


def _execute(db: Session, wf: Workflow, definition: WorkflowDefinition, step: WorkflowStep) -> str:
    sdef = definition.step(step.key)
    sctx = StepContext(db, wf, step, definition, sdef)
    step.status = "running"
    step.attempts += 1
    step.started_at = step.started_at or utcnow()
    step.error = None
    if sdef.input_fn:
        step.input = audit_service.json_safe(sdef.input_fn(sctx))
    db.commit()
    t0 = time.perf_counter()
    try:
        result = sdef.handler(sctx)
    except FlowException as fe:
        db.commit()  # keep context the handler recorded before raising
        return _on_exception(sctx, fe)
    except Exception as exc:  # noqa: BLE001 - classified by the exception engine
        db.rollback()
        return _on_exception(sctx, FlowException("UNEXPECTED_ERROR", f"{type(exc).__name__}: {exc}"))
    return _apply(sctx, result, int((time.perf_counter() - t0) * 1000))


def _apply(sctx: StepContext, result: StepResult, duration_ms: int) -> str:
    db, wf, step = sctx.db, sctx.workflow, sctx.step
    if result.ctx_patch:
        sctx.set(**result.ctx_patch)
    step.output = audit_service.json_safe(result.output)
    step.decision = result.decision
    step.reason = result.reason
    if result.status == "wait_human":
        from app.services import approvals as approval_service

        approval_service.open_approval(sctx, result.approval)
        return "stop"
    recovered = exception_engine.mark_recovered(db, step)
    if result.status == "skipped":
        step.status = "skipped"
    else:
        step.status = "resolved" if recovered else "completed"
    step.completed_at = utcnow()
    sctx.audit(f"step.{step.status}", actor_type="system", actor="FlowForge Engine",
               input={"step": step.key, "attempt": step.attempts}, output=step.output, result="ok",
               reason=result.reason or result.decision, status=step.status, duration_ms=duration_ms)
    db.commit()
    return "continue"


def _on_exception(sctx: StepContext, fe: FlowException) -> str:
    db, wf, step = sctx.db, sctx.workflow, sctx.step
    outcome = exception_engine.handle(sctx, fe)
    if outcome.kind == "retry":
        step.status = "pending"
        db.commit()
        return "continue"
    if outcome.kind == "resolved":
        if outcome.patch:
            sctx.set(**outcome.patch)
        step.status = "pending"
        if outcome.rewind_to:
            db.commit()
            rewind(db, wf, outcome.rewind_to)
        db.commit()
        return "continue"
    if outcome.kind == "waiting_human":
        step.status = "waiting_human"
        step.error = fe.message
        wf.status = "waiting_human"
        db.commit()
        return "stop"
    step.status = "failed"
    step.error = fe.message
    wf.status = "failed"
    wf.error = f"{fe.code}: {fe.message}"
    sctx.audit("workflow.failed", reason=wf.error, result="failed", status="failed",
               input={"step": step.key}, output={"exception": fe.code})
    db.commit()
    return "stop"


def _finish(db: Session, wf: Workflow, definition: WorkflowDefinition) -> None:
    unmet = definition.completion_criteria(db, wf)
    if unmet:
        wf.status = "failed"
        wf.error = "Completion criteria not met: " + "; ".join(unmet)
        audit_service.record(db, org_id=wf.org_id, workflow_id=wf.id, actor_type="system", actor="FlowForge Engine",
                             action="workflow.failed", result="failed", reason=wf.error, status="failed")
    else:
        wf.status = "completed"
        wf.completed_at = utcnow()
        audit_service.record(db, org_id=wf.org_id, workflow_id=wf.id, actor_type="system", actor="FlowForge Engine",
                             action="workflow.completed", output={"outcome": wf.outcome}, result="ok",
                             reason="All steps finished and completion criteria satisfied", status="completed")
    db.commit()


def cancel(db: Session, wf: Workflow, actor: str, reason: str) -> None:
    wf.status = "cancelled"
    wf.completed_at = utcnow()
    wf.error = reason
    for s in steps_of(db, wf):
        if s.status in ("pending", "waiting_human", "running"):
            s.status = "skipped"
            s.reason = s.reason or f"Workflow cancelled: {reason}"
    for a in db.query(Approval).filter(Approval.workflow_id == wf.id, Approval.status == "pending").all():
        a.status = "rejected"
        a.decision_note = f"Workflow cancelled: {reason}"
        a.decided_at = utcnow()
        a.decided_by = actor
    for e in db.query(WorkflowException).filter(WorkflowException.workflow_id == wf.id,
                                                WorkflowException.status.in_(["awaiting_review", "escalated"])).all():
        e.status = "rejected"
        e.resolved_at = utcnow()
        e.resolved_by = actor
    audit_service.record(db, org_id=wf.org_id, workflow_id=wf.id, actor_type="user", actor=actor,
                         action="workflow.cancelled", reason=reason, status="cancelled")
    db.commit()


def retry_failed(db: Session, wf: Workflow, actor: str) -> None:
    step = next((s for s in steps_of(db, wf) if s.status == "failed"), None)
    if step is None:
        step = next_step(db, wf)
    if step is not None:
        step.status = "pending"
        step.error = None
        for e in db.query(WorkflowException).filter(WorkflowException.step_id == step.id,
                                                    WorkflowException.status == "failed").all():
            e.status = "retrying"
            e.resolved_by = actor
            e.resolution = f"Retry requested by {actor}"
    wf.status = "running"
    wf.error = None
    audit_service.record(db, org_id=wf.org_id, workflow_id=wf.id, actor_type="user", actor=actor,
                         action="workflow.retry_requested", input={"step": step.key if step else None},
                         reason="Operator retry after failure", status="running")
    db.commit()
