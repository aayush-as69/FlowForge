"""One inbox for everything waiting on a person: approvals, exceptions that need review, and failed automations."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.core.db import get_db, utcnow
from app.core.security import has_permission, require
from app.models import Approval, Workflow, WorkflowException
from app.services import approvals as approval_service

router = APIRouter(prefix="/action-center", tags=["action-center"])

OVERDUE_HOURS = 24
STALE_EXCEPTIONS = ("awaiting_review", "escalated", "failed")


def _age_hours(ts) -> float:
    if ts is None:
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=utcnow().tzinfo)
    return round((utcnow() - ts).total_seconds() / 3600, 1)


@router.get("")
def action_center(db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    items: list[dict] = []
    if has_permission(user.role, "approvals:read"):
        rows = (db.query(Approval, Workflow).join(Workflow, Workflow.id == Approval.workflow_id)
                .filter(Workflow.org_id == user.org_id, Approval.status == "pending").all())
        for a, w in rows:
            problem = approval_service.can_decide(user, a, w)
            age = _age_hours(a.created_at)
            items.append({"type": "approval", "id": a.id, "workflow_id": w.id, "workflow_ref": ser.wf_ref(w.id), "title": a.title,
                          "summary": a.summary, "risk_level": a.risk_level, "level": a.level, "assigned_role": a.assigned_role,
                          "escalated": a.escalated, "age_hours": age, "overdue": age >= OVERDUE_HOURS, "mine": problem is None,
                          "blocked_reason": problem, "options": a.options, "created_at": a.created_at})
    if has_permission(user.role, "exceptions:read"):
        rows = (db.query(WorkflowException, Workflow).join(Workflow, Workflow.id == WorkflowException.workflow_id)
                .filter(Workflow.org_id == user.org_id, WorkflowException.status.in_(STALE_EXCEPTIONS)).all())
        for e, w in rows:
            age = _age_hours(e.detected_at)
            items.append({"type": "exception", "id": e.id, "workflow_id": w.id, "workflow_ref": ser.wf_ref(w.id),
                          "title": w.title, "summary": e.message, "code": e.code, "severity": e.severity, "status": e.status,
                          "age_hours": age, "overdue": age >= OVERDUE_HOURS, "mine": has_permission(user.role, "workflows:operate"),
                          "created_at": e.detected_at})
    seen_wf = {i["workflow_id"] for i in items if i["type"] == "exception"}
    failed = db.query(Workflow).filter(Workflow.org_id == user.org_id, Workflow.status == "failed")
    if user.role == "requester":
        failed = failed.filter(False)
    for w in failed.order_by(Workflow.created_at.desc()).limit(50):
        if w.id in seen_wf:
            continue
        age = _age_hours(w.completed_at or w.created_at)
        items.append({"type": "failed_workflow", "id": w.id, "workflow_id": w.id, "workflow_ref": ser.wf_ref(w.id), "title": w.title,
                      "summary": w.error or "Workflow failed", "age_hours": age, "overdue": age >= OVERDUE_HOURS,
                      "mine": has_permission(user.role, "workflows:operate"), "created_at": w.completed_at or w.created_at})
    # what needs me first: overdue, then mine, then oldest
    items.sort(key=lambda i: (not i["overdue"], not i["mine"], -i["age_hours"]))
    counts = {"approvals": sum(i["type"] == "approval" for i in items), "exceptions": sum(i["type"] == "exception" for i in items),
              "failed": sum(i["type"] == "failed_workflow" for i in items), "overdue": sum(i["overdue"] for i in items),
              "mine": sum(i["mine"] for i in items)}
    return {"counts": counts, "items": items[:200]}
