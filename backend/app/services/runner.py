"""Background execution with renewable, database-backed workflow ownership leases."""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from app.core import db as database
from app.core.config import settings
from app.core.db import utcnow
from app.models import Workflow, WorkflowStep
from app.workflows import engine as wf_engine

log = logging.getLogger("flowforge.runner")
_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="wf")
LEASE_SECONDS = 600
HEARTBEAT_SECONDS = 60


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


def _renew_lease(workflow_id: int, owner: str) -> bool:
    session = database.SessionLocal()
    try:
        updated = (session.query(Workflow)
                   .filter(Workflow.id == workflow_id, Workflow.runner_owner == owner,
                           Workflow.status.notin_(["completed", "cancelled"]))
                   .update({"runner_lease_until": utcnow() + timedelta(seconds=LEASE_SECONDS)},
                           synchronize_session=False))
        session.commit()
        return updated == 1
    finally:
        session.close()


def _heartbeat(workflow_id: int, owner: str, stop: threading.Event) -> None:
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            if not _renew_lease(workflow_id, owner):
                log.warning("workflow %s lease no longer owned by this runner", workflow_id)
                return
        except Exception:
            log.exception("workflow %s lease heartbeat failed", workflow_id)


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
    stop_heartbeat = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat, args=(workflow_id, owner, stop_heartbeat),
                                 name=f"wf-lease-{workflow_id}", daemon=True)
    heartbeat.start()
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
        stop_heartbeat.set()
        heartbeat.join(timeout=2)
        _release(workflow_id, owner)


def submit(workflow_id: int) -> None:
    if settings.sync_runner:
        _run(workflow_id)
    else:
        _executor.submit(_run, workflow_id)


def resume_interrupted() -> int:
    """After restart, submit persisted workflows; active leases prevent duplicate execution."""
    session = database.SessionLocal()
    try:
        ids = [w.id for w in session.query(Workflow).filter(Workflow.status.in_(["running", "pending"])).all()]
        # A crash between an approval commit and the resume leaves status=waiting_human with no step still waiting.
        waiting = session.query(Workflow).filter(Workflow.status == "waiting_human").all()
        for w in waiting:
            if not session.query(WorkflowStep.id).filter(WorkflowStep.workflow_id == w.id,
                                                         WorkflowStep.status == "waiting_human").first():
                ids.append(w.id)
    finally:
        session.close()
    for wid in ids:
        submit(wid)
    return len(ids)
