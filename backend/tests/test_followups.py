"""Regression tests: demo seeding, approval claim, demo gating, audit verification."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import db as database
from app.core.config import settings
from app.main import app
from app.models import Approval, AuditEvent, User, Workflow
from app.services import approvals as approval_service
from app.services import audit, seed
from app.workflows import engine as wf_engine

from tests.test_review_regressions import LAPTOP_REQUEST, client_for


def test_demo_seeding_runs_and_leaves_a_verifiable_chain(db):
    seed.seed_history(db)
    assert db.query(Workflow).count() > 30
    result = audit.verify_chain(db, 1)
    assert result["ok"], result
    assert result["checked"] == db.query(AuditEvent).count()
    # history really is back-dated, written that way rather than updated afterwards
    oldest = db.query(AuditEvent).order_by(AuditEvent.ts).first()
    assert (audit.utcnow() - oldest.ts.replace(tzinfo=audit.utcnow().tzinfo)).days >= 1


def test_verify_endpoint_detects_tampering(db):
    seed.seed_history(db, count=3)
    admin = client_for("admin")
    ok = admin.get("/api/audit/verify").json()
    assert ok["ok"] and ok["checked"] > 0
    # bypass the immutability trigger the way a database owner could, then check it is noticed
    with database.engine.begin() as conn:
        conn.execute(text("DROP TRIGGER audit_events_immutable_update"))
        conn.execute(text("UPDATE audit_events SET reason = 'edited' WHERE id = (SELECT MIN(id) + 5 FROM audit_events)"))
    bad = admin.get("/api/audit/verify").json()
    assert not bad["ok"] and bad["problem_count"] == 1


def test_audit_verify_requires_audit_permission(db):
    assert client_for("requester").get("/api/audit/verify").status_code == 403
    assert client_for("auditor").get("/api/audit/verify").status_code == 200




def test_stale_second_decision_is_refused(db, users):
    from app.services import requests as rs
    req = rs.create_request(db, users["requester"], text=LAPTOP_REQUEST, fields=None, source="text", demo_faults=[])
    wf = rs.start_workflow(db, req, users["requester"], step_delay=0)
    wf_engine.run(db, wf.id)
    approval = db.query(Approval).filter(Approval.workflow_id == wf.id, Approval.status == "pending").first()
    stale = database.SessionLocal()
    try:
        stale_copy = stale.get(Approval, approval.id)  # a second request that loaded the approval while pending
        manager = db.query(User).filter(User.email == "manager@flowforge.demo").one()
        approval_service.decide(db, approval, manager, "approve", "ok", None)
        db.commit()
        assert stale_copy.status == "pending"  # the stale object still believes it
        with pytest.raises(approval_service.ApprovalError) as exc:
            approval_service.decide(stale, stale_copy, stale.get(User, manager.id), "reject", "too late", None)
        assert exc.value.status == 409
    finally:
        stale.close()


def test_demo_scenarios_need_demo_run(db, monkeypatch):
    requester = client_for("requester")
    assert requester.get("/api/functions/procurement/scenarios").json() == []
    assert requester.post("/api/functions/procurement/demo", json={"scenario": "routine"}).status_code == 403
    assert "demo:run" not in requester.get("/api/auth/me").json()["permissions"]
    manager = client_for("manager")
    assert "demo:run" in manager.get("/api/auth/me").json()["permissions"]
    assert manager.get("/api/functions/procurement/scenarios").json()
    assert manager.post("/api/functions/procurement/demo", json={"scenario": "routine"}).status_code == 202


def test_demo_mode_off_disables_demo_for_everyone(db, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    admin = client_for("admin")
    assert "demo:run" not in admin.get("/api/auth/me").json()["permissions"]
    assert admin.get("/api/functions/procurement/scenarios").json() == []
    assert admin.post("/api/functions/procurement/demo", json={"scenario": "routine"}).status_code == 403


def test_file_sqlite_gets_a_connection_per_session_with_wal(tmp_path):
    engine = database.make_engine(f"sqlite:///{tmp_path / 'ff.db'}")
    with engine.connect() as c1, engine.connect() as c2:
        assert c1.connection.dbapi_connection is not c2.connection.dbapi_connection
        assert c1.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
    engine.dispose()
