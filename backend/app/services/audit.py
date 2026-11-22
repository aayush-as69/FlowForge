import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.core.db import utcnow


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))


def _canonical(event: AuditEvent) -> str:
    payload = {
        "org_id": event.org_id,
        "workflow_id": event.workflow_id,
        "ts": event.ts.isoformat() if event.ts else None,
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
        duration_ms=duration_ms, ts=utcnow(),
        prev_hash=previous.event_hash if previous else None,
        event_hash="",
    )
    event.event_hash = hashlib.sha256(_canonical(event).encode("utf-8")).hexdigest()
    db.add(event)
    db.flush()
    return event
