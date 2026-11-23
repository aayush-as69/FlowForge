from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.core.db import get_db
from app.core.security import require
from app.models import Approval, AuditEvent, Request, Workflow, WorkflowStep
from app.services import approvals as approval_service
from app.services import explain_workflow
from app.services import runner
from app.workflows import engine as wf_engine

router = APIRouter(tags=["workflows"])
steps_router = APIRouter(prefix="/workflow-steps", tags=["workflows"])


def _visible(db: Session, user, wid: int) -> Workflow:
    wf = db.get(Workflow, wid)
    if wf is None or wf.org_id != user.org_id:
        raise HTTPException(404, "Workflow not found.")
    if user.role == "requester" and (wf.request is None or wf.request.requester_id != user.id):
        raise HTTPException(404, "Workflow not found.")
    return wf


@router.get("/workflows")
def list_workflows(status: str | None = None, function: str | None = None, q: str | None = None,
                   page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    query = db.query(Workflow).filter(Workflow.org_id == user.org_id)
    if user.role == "requester":
        query = query.join(Request, Request.id == Workflow.request_id).filter(Request.requester_id == user.id)
    if status == "active":
        query = query.filter(Workflow.status.in_(["pending", "running", "waiting_human"]))
    elif status:
        query = query.filter(Workflow.status == status)
    if function:
        query = query.filter(Workflow.function_key == function)
    if q:
        like = f"%{q.strip()}%"
        conds = [Workflow.title.ilike(like)]
        if q.strip().upper().startswith("WF-") and q.strip()[3:].isdigit():
            conds.append(Workflow.id == int(q.strip()[3:]) - 1000)
        query = query.filter(or_(*conds))
    total = query.count()
    rows = query.order_by(Workflow.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    pend = dict(db.query(Approval.workflow_id, func.count()).filter(Approval.status == "pending",
                                                                     Approval.workflow_id.in_([w.id for w in rows] or [0]))
                .group_by(Approval.workflow_id).all())
    return ser.page([ser.ser_workflow(w, pending=pend.get(w.id, 0)) for w in rows], total, page, page_size)


@router.get("/workflows/{wid}/explanation")
def explain_workflow_route(wid: int, db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    return explain_workflow.explain(db, _visible(db, user, wid))


@router.get("/workflows/{wid}")
def get_workflow(wid: int, db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    wf = _visible(db, user, wid)
    detail = ser.ser_workflow_detail(db, wf)
    for a in detail["approvals"]:
        problem = approval_service.can_decide(user, db.get(Approval, a["id"]), wf)
        a["can_decide"], a["cannot_decide_reason"] = problem is None, problem
    return detail


@router.get("/workflows/{wid}/steps")
def get_steps(wid: int, db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    wf = _visible(db, user, wid)
    return [ser.ser_step(s) for s in wf_engine.steps_of(db, wf)]


@router.get("/workflows/{wid}/audit")
def get_audit(wid: int, db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    wf = _visible(db, user, wid)
    rows = db.query(AuditEvent).filter(AuditEvent.workflow_id == wf.id).order_by(AuditEvent.id).all()
    return [ser.ser_audit(e) for e in rows]


@router.post("/workflows/{wid}/retry")
def retry(wid: int, bg: BackgroundTasks, db: Session = Depends(get_db), user=Depends(require("workflows:operate"))):
    wf = _visible(db, user, wid)
    if wf.status != "failed":
        raise HTTPException(409, f"Only failed workflows can be retried (this one is {wf.status}).")
    wf_engine.retry_failed(db, wf, user.name)
    bg.add_task(runner.submit, wf.id)
    return {"ok": True, "status": "running"}


@router.post("/workflows/{wid}/cancel")
def cancel(wid: int, db: Session = Depends(get_db), user=Depends(require("workflows:operate"))):
    wf = _visible(db, user, wid)
    if wf.status in ("completed", "cancelled"):
        raise HTTPException(409, f"Workflow is already {wf.status}.")
    wf_engine.cancel(db, wf, user.name, f"Cancelled by {user.name}")
    return {"ok": True, "status": "cancelled"}


@steps_router.get("/{step_id}")
def get_step(step_id: int, db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    step = db.get(WorkflowStep, step_id)
    if step is None:
        raise HTTPException(404, "Step not found.")
    _visible(db, user, step.workflow_id)
    return ser.ser_step(step)
