import contextlib
import contextvars
import hashlib
import json
from datetime import timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.core.db import utcnow


_offset: contextvars.ContextVar[timedelta | None] = contextvars.ContextVar("audit_clock_offset", default=None)


@contextlib.contextmanager
def clock_offset(delta: timedelta):
    """Stamp events written inside the block ``delta`` in the past (demo seeding only).

    Audit rows are immutable, so history can't be back-dated afterwards; it has to be written that way.
    """
    token = _offset.set(delta)
    try:
        yield
    finally:
        _offset.reset(token)


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))


def _iso(ts):
    """Timestamps are hashed as UTC; SQLite hands them back naive and Postgres in the session zone."""
    if ts is None:
        return None
    ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
    return ts.isoformat()


def _canonical(event: AuditEvent) -> str:
    payload = {
        "org_id": event.org_id,
        "workflow_id": event.workflow_id,
        "ts": _iso(event.ts),
        "actor_type": event.actor_type,
        "actor": event.actor,
        "action": event.action,
        "input": event.input,
        "output": event.output,
        "result": event.result,
        "reason": event.reason,
        "status": event.status,
        "duration_ms": event.duration_ms,
        "prev_hash": event.prev_hash,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def record(
    db: Session,
    *,
    org_id: int,
    workflow_id: int | None,
    actor_type: str,
    actor: str,
    action: str,
    input: Any = None,
    output: Any = None,
    result: str = "ok",
    reason: str | None = None,
    status: str = "recorded",
    duration_ms: int | None = None,
) -> AuditEvent:
    """Append an audit event to a tamper-evident hash chain.

    Database triggers installed by ``init_db`` reject UPDATE/DELETE on audit_events, so the
    application cannot rewrite history after the event has been committed.
    """
    previous = (db.query(AuditEvent)
                .filter(AuditEvent.org_id == org_id)
                .order_by(AuditEvent.id.desc())
                .first())
    event = AuditEvent(
        org_id=org_id, workflow_id=workflow_id, actor_type=actor_type, actor=actor, action=action,
        input=json_safe(input), output=json_safe(output), result=result, reason=reason, status=status,
        duration_ms=duration_ms, ts=utcnow() - offset if (offset := _offset.get()) else utcnow(),
        prev_hash=previous.event_hash if previous else None,
        event_hash="",
    )
    event.event_hash = hashlib.sha256(_canonical(event).encode("utf-8")).hexdigest()
    db.add(event)
    db.flush()
    return event


def verify_chain(db: Session, org_id: int, limit: int = 20) -> dict:
    """Recompute every event hash for an organisation and check each link points at a real earlier event.

    Detects edited rows, removed rows in the middle of the history and spliced-in rows. It cannot see events
    removed from the very end, and a database superuser can still rewrite everything consistently.
    Concurrent writers can legitimately fork the chain (two events share a predecessor); those are reported
    as ``forks`` for information and do not fail verification.
    """
    problems: list[dict] = []
    seen: set[str] = set()
    parents: dict[str, int] = {}
    checked = unsealed = 0
    rows = db.query(AuditEvent).filter(AuditEvent.org_id == org_id).order_by(AuditEvent.id)
    for event in rows.yield_per(500):
        if not event.event_hash:
            unsealed += 1
            continue
        checked += 1
        if hashlib.sha256(_canonical(event).encode("utf-8")).hexdigest() != event.event_hash:
            problems.append({"id": event.id, "problem": "content does not match its hash"})
        if event.prev_hash is not None:
            if event.prev_hash not in seen:
                problems.append({"id": event.id, "problem": "predecessor event is missing"})
            parents[event.prev_hash] = parents.get(event.prev_hash, 0) + 1
        seen.add(event.event_hash)
    return {"ok": not problems, "checked": checked, "unsealed": unsealed, "problem_count": len(problems),
            "problems": problems[:limit], "forks": sum(1 for n in parents.values() if n > 1)}
