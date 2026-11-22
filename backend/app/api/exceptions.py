from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.core.db import get_db
from app.core.security import require
from app.models import Workflow, WorkflowException

router = APIRouter(prefix="/exceptions", tags=["exceptions"])

GROUPS = {
    "auto_resolved": ["auto_resolved", "retrying", "resolving"],
    "awaiting_review": ["awaiting_review"],
    "escalated": ["escalated"],
    "failed": ["failed"],
    "resolved_by_human": ["resolved_by_human", "rejected"],
}


@router.get("/summary")
def summary(db: Session = Depends(get_db), user=Depends(require("exceptions:read"))):
    rows = (db.query(WorkflowException.status).join(Workflow, Workflow.id == WorkflowException.workflow_id)
            .filter(Workflow.org_id == user.org_id).all())
    counts = Counter(s for (s,) in rows)
    return {g: sum(counts.get(s, 0) for s in statuses) for g, statuses in GROUPS.items()}


@router.get("")
def list_exceptions(group: str = "all", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                    db: Session = Depends(get_db), user=Depends(require("exceptions:read"))):
    q = db.query(WorkflowException, Workflow).join(Workflow, Workflow.id == WorkflowException.workflow_id).filter(Workflow.org_id == user.org_id)
    if group != "all":
        if group not in GROUPS:
            raise HTTPException(422, "Unknown exception group.")
        q = q.filter(WorkflowException.status.in_(GROUPS[group]))
    total = q.count()
    rows = q.order_by(WorkflowException.detected_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ser.page([ser.ser_exception(e, w) for e, w in rows], total, page, page_size)


@router.get("/{eid}")
def get_exception(eid: int, db: Session = Depends(get_db), user=Depends(require("exceptions:read"))):
    e = db.get(WorkflowException, eid)
    wf = db.get(Workflow, e.workflow_id) if e is not None else None
    if e is None or wf is None or wf.org_id != user.org_id:
        raise HTTPException(404, "Exception not found.")
    return ser.ser_exception(e, wf)
