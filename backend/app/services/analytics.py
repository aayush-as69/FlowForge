"""Workflow analytics and a transparent savings estimate.

Counts, rates and latencies come from the database. The cost and savings figures are *estimates*: they apply the
assumptions in ``settings.roi`` (minutes of manual work, hourly cost, price per model/tool call) to recorded activity,
and the assumptions are returned with every response so nobody mistakes them for billing data.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import case, exists, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.models import Approval, Request, ToolExecution, Workflow, WorkflowException
from app.services.dashboard import _seconds_between

DONE_STATES = ("completed", "failed", "cancelled")


def _pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def _approval_latency(db: Session, org_id: int, since) -> dict:
    base = [Workflow.org_id == org_id, Approval.status != "pending", Approval.decided_at.isnot(None), Approval.created_at >= since]
    secs = _seconds_between(db, Approval.created_at, Approval.decided_at)
    q = db.query(Approval).join(Workflow, Workflow.id == Approval.workflow_id)
    n, avg = q.with_entities(func.count(Approval.id), func.avg(secs)).filter(*base).one()
    median = None
    if n:
        median = q.with_entities(secs).filter(*base).order_by(secs).offset((n - 1) // 2).limit(1).scalar()
    rows = (q.with_entities(Approval.assigned_role, func.count(Approval.id), func.avg(secs)).filter(*base)
            .group_by(Approval.assigned_role).all())
    by_role = sorted(({"role": r, "count": c, "avg_hours": round(float(a) / 3600, 2)} for r, c, a in rows),
                     key=lambda x: -x["avg_hours"])
    return {"decided": n, "avg_hours": round(float(avg) / 3600, 2) if avg is not None else None,
            "median_hours": round(float(median) / 3600, 2) if median is not None else None,
            "slowest_role": by_role[0] if by_role else None, "by_role": by_role}


def estimate_savings(*, completed: int, llm_calls: int, tool_calls: int, human_reviews: int) -> dict:
    a = settings.roi
    manual = completed * a["manual_minutes_per_request"] / 60 * a["hourly_cost"]
    ai = llm_calls * a["llm_call_cost"]
    tools = tool_calls * a["tool_call_cost"]
    human = human_reviews * a["human_review_minutes"] / 60 * a["hourly_cost"]
    actual = ai + tools + human
    hours_saved = max(completed * a["manual_minutes_per_request"] - human_reviews * a["human_review_minutes"], 0) / 60
    return {"currency": a["currency"], "manual_cost": round(manual, 2), "ai_cost": round(ai, 2), "api_cost": round(tools, 2),
            "human_cost": round(human, 2), "total_cost": round(actual, 2), "savings": round(manual - actual, 2),
            "hours_saved": round(hours_saved, 1), "assumptions": dict(a)}


def overview(db: Session, org_id: int, days: int = 30, function: str | None = None) -> dict:
    since = utcnow() - timedelta(days=days)
    wf = [Workflow.org_id == org_id, Workflow.created_at >= since]
    if function:
        wf.append(Workflow.function_key == function)
    by_status = dict(db.query(Workflow.status, func.count(Workflow.id)).filter(*wf).group_by(Workflow.status).all())
    total = sum(by_status.values())
    completed, failed = by_status.get("completed", 0), by_status.get("failed", 0)
    needs_human = exists().where(Approval.workflow_id == Workflow.id, Approval.status != "pending")
    automated = db.query(func.count(Workflow.id)).filter(*wf, Workflow.status == "completed", ~needs_human).scalar() or 0
    with_exc = (db.query(func.count(func.distinct(WorkflowException.workflow_id)))
                .join(Workflow, Workflow.id == WorkflowException.workflow_id).filter(*wf).scalar() or 0)

    reasons = (db.query(WorkflowException.code, func.count(WorkflowException.id),
                        func.sum(case((WorkflowException.status.in_(["auto_resolved", "resolved_by_human"]), 1), else_=0)))
               .join(Workflow, Workflow.id == WorkflowException.workflow_id).filter(*wf)
               .group_by(WorkflowException.code).order_by(func.count(WorkflowException.id).desc()).limit(8).all())

    day = func.date(Workflow.completed_at)
    series = {str(d): n for d, n in db.query(day, func.count(Workflow.id))
              .filter(*wf, Workflow.status == "completed", Workflow.completed_at.isnot(None)).group_by(day).all()}
    today = utcnow().date()
    daily = [{"date": (today - timedelta(days=i)).isoformat(), "completed": series.get((today - timedelta(days=i)).isoformat(), 0)}
             for i in range(min(days, 30) - 1, -1, -1)]

    tool_calls = (db.query(func.count(ToolExecution.id)).join(Workflow, Workflow.id == ToolExecution.workflow_id)
                  .filter(*wf, ToolExecution.status == "completed").scalar() or 0)
    llm_calls = (db.query(func.count(Request.id)).join(Workflow, Workflow.request_id == Request.id)
                 .filter(*wf, Request.extraction_engine != "heuristic").scalar() or 0)
    human_reviews = (db.query(func.count(Approval.id)).join(Workflow, Workflow.id == Approval.workflow_id)
                     .filter(*wf, Approval.status != "pending").scalar() or 0)
    secs = _seconds_between(db, Workflow.started_at, Workflow.completed_at)
    avg_dur = (db.query(func.avg(secs)).filter(*wf, Workflow.status == "completed", Workflow.started_at.isnot(None),
                                               Workflow.completed_at.isnot(None)).scalar())
    return {
        "window_days": days, "function": function,
        "volume": {"started": total, "completed": completed, "failed": failed, "cancelled": by_status.get("cancelled", 0),
                   "in_progress": total - sum(by_status.get(s, 0) for s in DONE_STATES)},
        "rates": {"success_pct": _pct(completed, completed + failed), "automation_pct": _pct(automated, completed),
                  "human_intervention_pct": _pct(completed - automated, completed), "exception_pct": _pct(with_exc, total)},
        "avg_duration_s": round(float(avg_dur), 1) if avg_dur is not None else None,
        "approval_latency": _approval_latency(db, org_id, since),
        "failure_reasons": [{"code": c, "count": n, "recovered": int(r or 0)} for c, n, r in reasons],
        "daily": daily,
        "roi": estimate_savings(completed=completed, llm_calls=llm_calls, tool_calls=tool_calls, human_reviews=human_reviews),
    }


def workflow_cost(db: Session, wf: Workflow) -> dict:
    tools = db.query(func.count(ToolExecution.id)).filter(ToolExecution.workflow_id == wf.id, ToolExecution.status == "completed").scalar() or 0
    human = db.query(func.count(Approval.id)).filter(Approval.workflow_id == wf.id, Approval.status != "pending").scalar() or 0
    llm = 1 if wf.request and wf.request.extraction_engine != "heuristic" else 0
    est = estimate_savings(completed=1 if wf.status == "completed" else 0, llm_calls=llm, tool_calls=tools, human_reviews=human)
    return {**est, "tool_calls": tools, "llm_calls": llm, "human_reviews": human, "counted_as_saving": wf.status == "completed"}
