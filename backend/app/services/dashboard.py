from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import exists, func
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import ApiMetric, Approval, AuditEvent, Integration, Workflow, WorkflowException

def _seconds_between(db: Session, start, end):
    """SQL expression for (end - start) in seconds, for both supported databases."""
    if db.get_bind().dialect.name == "sqlite":
        return (func.julianday(end) - func.julianday(start)) * 86400.0
    return func.extract("epoch", end - start)


def completed_stats(db: Session, org_id: int) -> dict:
    """Totals, automation share and duration stats for completed workflows, computed by the database."""
    done = [Workflow.org_id == org_id, Workflow.status == "completed"]
    total = db.query(func.count(Workflow.id)).filter(*done).scalar() or 0
    needs_human = exists().where(Approval.workflow_id == Workflow.id, Approval.status != "pending")
    automated = db.query(func.count(Workflow.id)).filter(*done, ~needs_human).scalar() or 0
    secs = _seconds_between(db, Workflow.started_at, Workflow.completed_at)
    timed = [*done, Workflow.started_at.isnot(None), Workflow.completed_at.isnot(None)]
    n, avg = db.query(func.count(Workflow.id), func.avg(secs)).filter(*timed).one()
    p95 = None
    if n >= 5:  # the 95th percentile row, fetched with ORDER BY/OFFSET rather than loading every duration
        p95 = db.query(secs).filter(*timed).order_by(secs).offset(int(n * 0.95) - 1).limit(1).scalar()
    return {"total": total, "automated": automated, "avg": round(float(avg), 1) if avg is not None else None,
            "p95": round(float(p95), 1) if p95 is not None else None}


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

    stats = completed_stats(db, org_id)
    rate = round(stats["automated"] / stats["total"] * 100) if stats["total"] else 0

    day_counts: dict[str, int] = defaultdict(int)
    window = (db.query(Workflow.completed_at)  # only the last seven days of completions, never the whole history
              .filter(Workflow.org_id == org_id, Workflow.status == "completed",
                      Workflow.completed_at >= start_of_day - timedelta(days=6)))
    for (completed_at,) in window:
        day_counts[completed_at.date().isoformat()] += 1
    series = [{"date": (start_of_day + timedelta(days=i - 6)).date().isoformat(),
               "completed": day_counts.get((start_of_day + timedelta(days=i - 6)).date().isoformat(), 0)} for i in range(7)]

    active_rows = (db.query(Workflow).filter(Workflow.org_id == org_id, Workflow.status.in_(ACTIVE))
                   .order_by(Workflow.created_at.desc()).limit(8).all())
    recent = (db.query(AuditEvent, Workflow.title).outerjoin(Workflow, Workflow.id == AuditEvent.workflow_id)
              .filter(AuditEvent.org_id == org_id, ~AuditEvent.action.like("tool.%"), ~AuditEvent.action.like("step.%"))
              .order_by(AuditEvent.id.desc()).limit(14).all())
    exc_counts = dict(db.query(WorkflowException.status, func.count())
                      .join(Workflow, Workflow.id == WorkflowException.workflow_id).filter(Workflow.org_id == org_id)
                      .group_by(WorkflowException.status).all())
    return {
        "metrics": {
            "active_workflows": active, "completed_today": completed_today, "pending_review": pending_review,
            "open_exceptions": open_exc, "automation_rate": rate, "human_intervention": 100 - rate if stats["total"] else 0,
            "completed_total": stats["total"], "avg_duration_s": stats["avg"],
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


def api_stats(db: Session, org_id: int) -> dict:
    """Calculate observability from only the authenticated organisation's request metrics."""
    rows = (db.query(ApiMetric).filter(ApiMetric.org_id == org_id)
            .order_by(ApiMetric.id.desc()).limit(5000).all())
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
    stats = completed_stats(db, org_id)
    return {
        "workflow_execution": {
            "completed": stats["total"],
            "failed": db.query(Workflow).filter(Workflow.org_id == org_id, Workflow.status == "failed").count(),
            "avg_duration_s": stats["avg"],
            "p95_duration_s": stats["p95"],
        },
        "agent_actions": {t: c for t, c in actors},
        "tool_calls": {r: c for r, c in tool_rows},
        "exceptions": {"total": exc_total, "retries": retries},
        "human_interventions": humans,
        "api": api_stats,
    }
