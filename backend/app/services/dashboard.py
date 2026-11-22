from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from datetime import timezone

from app.core.db import utcnow
from app.models import ApiMetric, Approval, AuditEvent, Integration, Workflow, WorkflowException

def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


ACTIVE = ("pending", "running", "waiting_human")
OPEN_EXC = ("awaiting_review", "escalated", "failed", "open")


def summary(db: Session, org_id: int) -> dict:
    now = utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    active = db.query(Workflow).filter(Workflow.org_id == org_id, Workflow.status.in_(ACTIVE)).count()
    completed_today = db.query(Workflow).filter(Workflow.org_id == org_id, Workflow.status == "completed",
                                                Workflow.completed_at >= start_of_day).count()
    pending_review = (db.query(Approval).join(Workflow, Workflow.id == Approval.workflow_id)
                      .filter(Workflow.org_id == org_id, Approval.status == "pending").count())
    open_exc = (db.query(WorkflowException).join(Workflow, Workflow.id == WorkflowException.workflow_id)
                .filter(Workflow.org_id == org_id, WorkflowException.status.in_(OPEN_EXC)).count())

    completed = db.query(Workflow).filter(Workflow.org_id == org_id, Workflow.status == "completed").all()
    needing_human = {wid for (wid,) in db.query(Approval.workflow_id).join(Workflow, Workflow.id == Approval.workflow_id)
                     .filter(Workflow.org_id == org_id, Approval.status != "pending").distinct()}
    automated = [w for w in completed if w.id not in needing_human]
    rate = round(len(automated) / len(completed) * 100) if completed else 0

    durations = [(w.completed_at - w.started_at).total_seconds() for w in completed if w.completed_at and w.started_at]
    day_counts: dict[str, int] = defaultdict(int)
    for w in completed:
        if w.completed_at and _aware(w.completed_at) >= start_of_day - timedelta(days=6):
            day_counts[w.completed_at.date().isoformat()] += 1
    series = [{"date": (start_of_day + timedelta(days=i - 6)).date().isoformat(),
               "completed": day_counts.get((start_of_day + timedelta(days=i - 6)).date().isoformat(), 0)} for i in range(7)]

    active_rows = (db.query(Workflow).filter(Workflow.org_id == org_id, Workflow.status.in_(ACTIVE))
                   .order_by(Workflow.created_at.desc()).limit(8).all())
    recent = (db.query(AuditEvent, Workflow.title).outerjoin(Workflow, Workflow.id == AuditEvent.workflow_id)
              .filter(AuditEvent.org_id == org_id, ~AuditEvent.action.like("tool.%"), ~AuditEvent.action.like("step.%"))
              .order_by(AuditEvent.id.desc()).limit(14).all())
    exc_counts = Counter(s for (s,) in db.query(WorkflowException.status)
                         .join(Workflow, Workflow.id == WorkflowException.workflow_id).filter(Workflow.org_id == org_id).all())
    return {
        "metrics": {
            "active_workflows": active, "completed_today": completed_today, "pending_review": pending_review,
            "open_exceptions": open_exc, "automation_rate": rate, "human_intervention": 100 - rate if completed else 0,
            "completed_total": len(completed), "avg_duration_s": round(statistics.mean(durations), 1) if durations else None,
        },
        "throughput": series,
        "active": [{"id": w.id, "title": w.title, "status": w.status, "current_step": w.current_step_key,
                    "created_at": w.created_at} for w in active_rows],
        "recent_activity": [{"id": e.id, "ts": e.ts, "actor": e.actor, "actor_type": e.actor_type, "action": e.action,
                             "reason": e.reason, "result": e.result, "workflow_id": e.workflow_id, "workflow": title}
                            for e, title in recent],
        "exception_counts": dict(exc_counts),
        "integrations": [{"key": i.key, "name": i.name, "status": i.status} for i in
                         db.query(Integration).filter(Integration.org_id == org_id).order_by(Integration.id)],
    }


def api_stats(db: Session) -> dict:
    """Calculate API observability from persisted request metrics, not process memory."""
    rows = db.query(ApiMetric).order_by(ApiMetric.id.desc()).limit(5000).all()
    lat = sorted(r.duration_ms for r in rows)
    failures = [r for r in rows if r.status_code >= 400]
    return {
        "requests": len(rows),
        "errors_4xx": sum(400 <= r.status_code < 500 for r in rows),
        "errors_5xx": sum(r.status_code >= 500 for r in rows),
        "p50_ms": round(lat[len(lat) // 2]) if lat else None,
        "p95_ms": round(lat[int(len(lat) * 0.95) - 1]) if len(lat) >= 5 else None,
        "recent_failures": [{"path": r.path, "status": r.status_code, "ms": r.duration_ms} for r in failures[:15]],
    }


def observability(db: Session, org_id: int, api_stats: dict) -> dict:
    """Metrics for one organisation. (api_stats are process-wide request counters, not tenant data.)"""
    step_events = db.query(AuditEvent.action, AuditEvent.duration_ms).filter(
        AuditEvent.org_id == org_id, AuditEvent.action.like("step.%"), AuditEvent.duration_ms.isnot(None)).all()
    by_step: dict[str, list[int]] = defaultdict(list)
    for action, ms in step_events:
        by_step[action].append(ms)
    tool_rows = (db.query(AuditEvent.result, func.count())
                 .filter(AuditEvent.org_id == org_id, AuditEvent.action.like("tool.%")).group_by(AuditEvent.result).all())
    actors = db.query(AuditEvent.actor_type, func.count()).filter(AuditEvent.org_id == org_id).group_by(AuditEvent.actor_type).all()
    org_exceptions = db.query(WorkflowException).join(Workflow, Workflow.id == WorkflowException.workflow_id).filter(Workflow.org_id == org_id)
    exc_total = org_exceptions.count()
    retries = org_exceptions.filter(WorkflowException.resolution.like("Automatic retry%")).count()
    humans = (db.query(Approval).join(Workflow, Workflow.id == Approval.workflow_id)
              .filter(Workflow.org_id == org_id, Approval.status != "pending").count())
    completed = db.query(Workflow).filter(Workflow.org_id == org_id, Workflow.status == "completed").all()
    durations = [(w.completed_at - w.started_at).total_seconds() for w in completed if w.completed_at and w.started_at]
    return {
        "workflow_execution": {
            "completed": len(completed),
            "failed": db.query(Workflow).filter(Workflow.org_id == org_id, Workflow.status == "failed").count(),
            "avg_duration_s": round(statistics.mean(durations), 1) if durations else None,
            "p95_duration_s": round(sorted(durations)[int(len(durations) * 0.95) - 1], 1) if len(durations) >= 5 else None,
        },
        "agent_actions": {t: c for t, c in actors},
        "tool_calls": {r: c for r, c in tool_rows},
        "exceptions": {"total": exc_total, "retries": retries},
        "human_interventions": humans,
        "api": api_stats,
    }
