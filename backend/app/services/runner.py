"""Background execution: long-running workflows never block API requests.

Runner ownership is persisted on the workflow row as a short lease. This makes duplicate
submissions safe across multiple API/worker processes and lets another worker recover work
left behind by a crashed process after the lease expires.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from app.core import db as database
from app.core.config import settings
from app.core.db import utcnow
from app.models import Workflow
from app.workflows import engine as wf_engine

log = logging.getLogger("flowforge.runner")
_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="wf")
LEASE_SECONDS = 600


def _claim(workflow_id: int, owner: str) -> bool:
    session = database.SessionLocal()
    try:
        now = utcnow()
        lease_until = now + timedelta(seconds=LEASE_SECONDS)
        updated = (session.query(Workflow)
                   .filter(Workflow.id == workflow_id,
                           Workflow.status.notin_(["completed", "cancelled"]),
                           (Workflow.runner_lease_until.is_(None) | (Workflow.runner_lease_until < now)))
                   .update({"runner_owner": owner, "runner_lease_until": lease_until}, synchronize_session=False))
        session.commit()
        return updated == 1
    finally:
        session.close()


def _release(workflow_id: int, owner: str) -> None:
    session = database.SessionLocal()
    try:
        session.query(Workflow).filter(Workflow.id == workflow_id, Workflow.runner_owner == owner).update(
            {"runner_owner": None, "runner_lease_until": None}, synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _run(workflow_id: int) -> None:
    owner = uuid.uuid4().hex
    if not _claim(workflow_id, owner):
        return
    session = database.SessionLocal()
    try:
        wf_engine.run(session, workflow_id)
    except Exception:  # noqa: BLE001
        log.exception("workflow %s crashed", workflow_id)
        session.rollback()
        wf = session.get(Workflow, workflow_id)
        if wf is not None and wf.status not in ("completed", "cancelled"):
            wf.status = "failed"
            wf.error = "Runner crashed unexpectedly; use Retry to resume from the last persisted state."
            session.commit()
    finally:
        session.close()
        _release(workflow_id, owner)


def submit(workflow_id: int) -> None:
    if settings.sync_runner:
        _run(workflow_id)
    else:
        _executor.submit(_run, workflow_id)


def resume_interrupted() -> int:
    """After a restart, submit persisted workflows; active leases prevent duplicate execution."""
    session = database.SessionLocal()
    try:
        ids = [w.id for w in session.query(Workflow).filter(Workflow.status.in_(["running", "pending"])).all()]
    finally:
        session.close()
    for wid in ids:
        submit(wid)
    return len(ids)
