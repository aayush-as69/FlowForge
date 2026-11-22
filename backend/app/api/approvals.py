from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.core.db import get_db
from app.core.security import require
from app.models import Approval, Workflow
from app.schemas.api import DecisionIn
from app.services import approvals as svc
from app.services import runner

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _load(db: Session, user, aid: int) -> tuple[Approval, Workflow]:
    """An approval is only visible to its own organisation; anything else is indistinguishable from 'not found'."""
    a = db.get(Approval, aid)
    w = db.get(Workflow, a.workflow_id) if a is not None else None
    if a is None or w is None or w.org_id != user.org_id:
        raise HTTPException(404, "Approval not found.")
    return a, w


@router.get("")
def list_approvals(status: str = "pending", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   db: Session = Depends(get_db), user=Depends(require("approvals:read"))):
    q = db.query(Approval, Workflow).join(Workflow, Workflow.id == Approval.workflow_id).filter(Workflow.org_id == user.org_id)
    if status == "pending":
        q = q.filter(Approval.status == "pending")
    elif status == "decided":
        q = q.filter(Approval.status != "pending")
    total = q.count()
    rows = q.order_by(Approval.level.desc(), Approval.created_at.desc() if status != "pending" else Approval.created_at.asc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    pending_total = (db.query(Approval).join(Workflow, Workflow.id == Approval.workflow_id)
                     .filter(Workflow.org_id == user.org_id, Approval.status == "pending").count())
    out = ser.page([{**ser.ser_approval(a, w), "can_decide": svc.can_decide(user, a, w) is None,
                     "cannot_decide_reason": svc.can_decide(user, a, w)} for a, w in rows], total, page, page_size)
    out["pending_total"] = pending_total
    return out


@router.get("/{aid}")
def get_approval(aid: int, db: Session = Depends(get_db), user=Depends(require("approvals:read"))):
    a, w = _load(db, user, aid)
    return {**ser.ser_approval(a, w), "can_decide": svc.can_decide(user, a, w) is None, "cannot_decide_reason": svc.can_decide(user, a, w)}


@router.post("/{aid}/decision")
def decide(aid: int, body: DecisionIn, bg: BackgroundTasks, db: Session = Depends(get_db), user=Depends(require("approvals:decide"))):
    a, _ = _load(db, user, aid)
    try:
        resume = svc.decide(db, a, user, body.action, body.note, body.modification)
    except svc.ApprovalError as err:
        db.rollback()
        raise HTTPException(err.status, str(err)) from err
    if resume:
        bg.add_task(runner.submit, a.workflow_id)
    return {"ok": True, "approval": ser.ser_approval(a), "workflow_resumed": resume}
