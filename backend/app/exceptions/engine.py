"""Exception engine: detect → classify → decide recoverability → retry / auto-resolve → escalate → record → resume.

Exceptions never simply terminate a workflow. Each exception *code* has a registered spec that
declares how it is classified and which recovery strategies may be attempted, in order."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.config import settings
from app.core.db import utcnow
from app.models import WorkflowException
from app.workflows.types import ApprovalSpec, FlowException


@dataclass
class ResolverResult:
    ok: bool
    message: str
    patch: dict = field(default_factory=dict)  # merged into workflow context (e.g. overrides)
    rewind_to: str | None = None  # re-run the workflow from this step
    data: dict = field(default_factory=dict)


@dataclass
class ExceptionSpec:
    code: str
    category: str  # integration | policy | vendor | data | system | verification
    description: str = ""
    severity: str = "medium"
    recoverable: bool = True
    max_retries: int = 0
    resolvers: list[Callable[[Any, FlowException], ResolverResult]] = field(default_factory=list)
    human_review: bool = True
    review_builder: Callable[[Any, FlowException, list[dict]], ApprovalSpec] | None = None
    review_role: str = "approver"
    on_approve: Callable[[dict], dict] | None = None  # details -> override patch
    on_modify: Callable[[dict, dict], dict] | None = None  # details, modification -> override patch
    # details, modification -> error message (or None when acceptable). Runs before anything is applied, so a
    # reviewer's "modify" is either honoured exactly as chosen or refused with a clear reason.
    validate_modify: Callable[[dict, dict], str | None] | None = None


@dataclass
class Outcome:
    kind: str  # retry | resolved | waiting_human | failed
    message: str = ""
    patch: dict = field(default_factory=dict)
    rewind_to: str | None = None


REGISTRY: dict[str, ExceptionSpec] = {}


def register(spec: ExceptionSpec) -> ExceptionSpec:
    REGISTRY[spec.code] = spec
    return spec


def spec_for(code: str) -> ExceptionSpec:
    return REGISTRY.get(code) or REGISTRY["UNEXPECTED_ERROR"]


# --- generic, function-independent exception classes ---------------------------------------
register(ExceptionSpec("INTEGRATION_TIMEOUT", "integration", "An enterprise system did not respond in time",
                       severity="low", max_retries=2, review_role="admin"))
register(ExceptionSpec("INTEGRATION_UNAVAILABLE", "integration", "An enterprise system is disconnected",
                       severity="high", max_retries=1, review_role="admin"))
register(ExceptionSpec("PERMISSION_BOUNDARY", "system", "An agent attempted an action outside its permission boundary",
                       severity="high", recoverable=False, human_review=False))
register(ExceptionSpec("UNEXPECTED_ERROR", "system", "Unclassified runtime error",
                       severity="high", recoverable=False, human_review=False))


def handle(sctx, fe: FlowException) -> Outcome:
    from app.services import approvals as approval_service

    spec = spec_for(fe.code)
    recoverable = spec.recoverable if fe.recoverable is None else fe.recoverable
    db, wf, step = sctx.db, sctx.workflow, sctx.step

    # one exception record per incident: retries of the same failure are folded into it
    exc = (db.query(WorkflowException)
           .filter(WorkflowException.workflow_id == wf.id, WorkflowException.step_id == step.id,
                   WorkflowException.code == fe.code, WorkflowException.status == "retrying")
           .order_by(WorkflowException.id.desc()).first())
    if exc is not None:
        exc.attempts += 1
        exc.message = fe.message
        exc.details = fe.details
    else:
        exc = WorkflowException(
            workflow_id=wf.id, step_id=step.id, code=fe.code, category=spec.category, severity=spec.severity,
            recoverable=recoverable, status="open", message=fe.message, details=fe.details, attempts=1,
            resolution_trace=[],
        )
        db.add(exc)
    db.flush()
    sctx.audit("exception.detected", actor_type="system", actor="Exception Engine",
               input={"step": step.key, "code": fe.code, "attempt": exc.attempts},
               output={"category": spec.category, "recoverable": recoverable, "severity": spec.severity},
               result="exception", reason=fe.message, status="open")

    trace: list[dict] = list(exc.resolution_trace or [])

    def log(kind: str, ok: bool, message: str):
        trace.append({"action": kind, "ok": ok, "message": message, "at": utcnow().isoformat()})
        exc.resolution_trace = list(trace)

    # 1. retry (transient problems)
    if recoverable and exc.attempts <= spec.max_retries:
        backoff = settings.retry_backoff * exc.attempts
        exc.status = "retrying"
        exc.resolution = f"Automatic retry {exc.attempts}/{spec.max_retries} after {backoff:.1f}s backoff"
        log("retry", True, exc.resolution)
        sctx.audit("exception.retry", actor="Exception Engine", input={"code": fe.code, "attempt": exc.attempts},
                   output={"backoff_s": backoff}, reason=fe.message, status="retrying")
        db.commit()
        if backoff > 0:
            time.sleep(backoff)
        return Outcome("retry", exc.resolution)
    if recoverable and spec.max_retries:
        log("retry", False, f"Retries exhausted after {spec.max_retries} attempt(s)")

    # 2. automated resolution (alternatives, recalculation, …)
    if recoverable:
        for resolver in spec.resolvers:
            result = resolver(sctx, fe)
            log(resolver.__name__, result.ok, result.message)
            if result.ok:
                exc.status = "resolving"
                exc.resolution = result.message
                sctx.audit("exception.auto_resolved", actor="Exception Engine", input={"code": fe.code},
                           output={"patch": result.patch, "rewind_to": result.rewind_to, **result.data},
                           reason=result.message, status="resolving")
                db.commit()
                return Outcome("resolved", result.message, result.patch, result.rewind_to)

    # 3. escalate to a human with full context
    if spec.human_review and (recoverable or spec.review_builder):
        if spec.review_builder:
            approval_spec = spec.review_builder(sctx, fe, trace)
        else:
            approval_spec = ApprovalSpec(
                title=f"{spec.description or fe.code}: {wf.title}",
                summary=fe.message,
                reason="Automatic recovery was attempted and did not succeed.",
                recommendation="Review the failure, then approve to retry, or reject to stop the workflow.",
                risk="Workflow is paused until a decision is made.",
                supporting_data={"trace": trace, "details": fe.details},
                assigned_role=spec.review_role, kind="exception_review", options=["approve", "reject", "escalate"],
            )
        approval_spec.kind = "exception_review"
        exc.status = "awaiting_review"
        exc.resolution = "Automated recovery could not safely resolve this; human review requested"
        log("escalate", True, f"Human review requested from role '{approval_spec.assigned_role}'")
        db.flush()
        approval_service.open_approval(sctx, approval_spec, exception=exc)
        return Outcome("waiting_human", exc.resolution)

    # 4. unrecoverable
    exc.status = "failed"
    exc.resolved_at = utcnow()
    exc.resolution = "Not recoverable automatically; no safe human override defined"
    log("fail", False, exc.resolution)
    db.commit()
    return Outcome("failed", fe.message)


def mark_recovered(db, step) -> bool:
    """Called when a step finally completes: close out exceptions that were being recovered."""
    rows = db.query(WorkflowException).filter(WorkflowException.step_id == step.id).all()
    recovered = False
    for exc in rows:
        if exc.status in ("retrying", "resolving"):
            exc.status = "resolved_by_human" if exc.resolved_by else "auto_resolved"
            exc.resolved_at = utcnow()
            if exc.status == "auto_resolved":
                exc.resolved_by = "FlowForge (automated)"
            recovered = True
        elif exc.status in ("auto_resolved", "resolved_by_human"):
            recovered = True
    return recovered
