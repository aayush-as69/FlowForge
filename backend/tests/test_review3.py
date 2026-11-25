"""Regression tests for the third review: login audit pollution, request ownership, resume after crash, dotenv, metrics."""
import os

from fastapi.testclient import TestClient

from app.core import db as database
from app.main import app, drain_metrics
from app.models import ApiMetric, AuditEvent, Workflow
from app.services import runner

from tests.test_review_regressions import LAPTOP_REQUEST, client_for


def test_unknown_email_login_failures_never_touch_any_audit_trail(db, users):
    anon = TestClient(app, raise_server_exceptions=False)
    before = db.query(AuditEvent).count()
    for i in range(3):
        assert anon.post("/api/auth/login", json={"email": f"nobody{i}@x.test", "password": "pw"}).status_code == 401
    db.expire_all()
    assert db.query(AuditEvent).count() == before
    # a real account's failed attempt is still audited, in that account's own organisation
    real = users["admin"]
    assert anon.post("/api/auth/login", json={"email": real.email, "password": "wrong"}).status_code == 401
    db.expire_all()
    row = db.query(AuditEvent).filter(AuditEvent.action == "auth.login_failed").order_by(AuditEvent.id.desc()).first()
    assert row is not None and row.org_id == real.org_id and row.actor == real.email


def test_only_the_owner_or_an_admin_can_edit_or_execute_a_request(db, users):
    req_client, mgr, admin = client_for("requester"), client_for("manager"), client_for("admin")
    rid = req_client.post("/api/requests", json={"text": LAPTOP_REQUEST}).json()["id"]
    assert mgr.patch(f"/api/requests/{rid}", json={"purpose": "hijacked"}).status_code == 403
    assert mgr.post(f"/api/requests/{rid}/execute").status_code == 403
    assert req_client.patch(f"/api/requests/{rid}", json={"purpose": "mine"}).status_code == 200
    assert admin.patch(f"/api/requests/{rid}", json={"purpose": "admin fix"}).status_code == 200
    assert mgr.get(f"/api/requests/{rid}").status_code == 200  # reading is still allowed


def test_decided_but_unresumed_workflows_are_picked_up_after_a_restart(db, users, monkeypatch):
    from app.models import WorkflowStep
    from tests.test_roadmap1 import _run
    wf = _run(db, users, LAPTOP_REQUEST, "requester")
    waiting = db.query(Workflow).filter(Workflow.status == "waiting_human").all()
    assert waiting, "fixture should leave a workflow waiting for a person"
    seen = []
    monkeypatch.setattr(runner, "submit", lambda wid: seen.append(wid))
    still_waiting = {w.id for w in waiting if db.query(WorkflowStep).filter_by(workflow_id=w.id, status="waiting_human").count()}
    runner.resume_interrupted()
    assert not (set(seen) & still_waiting)  # genuinely waiting workflows are left alone
    # simulate a crash right after the approval commit: step completed, workflow still marked waiting_human
    victim = next(iter(still_waiting))
    for st in db.query(WorkflowStep).filter_by(workflow_id=victim, status="waiting_human").all():
        st.status = "completed"
    db.commit()
    seen.clear()
    runner.resume_interrupted()
    assert victim in seen
    assert wf is not None


def test_dotenv_handles_comments_and_export(tmp_path, monkeypatch):
    from app.core import config
    env = tmp_path / ".env"
    env.write_text('export FF_T_A=one # trailing\nFF_T_B="two # kept" # gone\nFF_T_C=th#ree\nFF_T_D=\'four\'\n# FF_T_E=no\n')
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
    for k in ("FF_T_A", "FF_T_B", "FF_T_C", "FF_T_D", "FF_T_E"):
        monkeypatch.delenv(k, raising=False)
    config._load_dotenv()
    try:
        assert os.environ["FF_T_A"] == "one"
        assert os.environ["FF_T_B"] == "two # kept"
        assert os.environ["FF_T_C"] == "th#ree"
        assert os.environ["FF_T_D"] == "four"
        assert "FF_T_E" not in os.environ
    finally:
        for k in ("FF_T_A", "FF_T_B", "FF_T_C", "FF_T_D"):
            os.environ.pop(k, None)


def test_metrics_do_not_block_the_response_and_still_arrive(db, users):
    admin = client_for("admin")
    drain_metrics()
    with database.SessionLocal() as s:
        before = s.query(ApiMetric).count()
    assert admin.get("/api/dashboard/summary").status_code == 200
    drain_metrics()
    with database.SessionLocal() as s:
        assert s.query(ApiMetric).count() == before + 1
