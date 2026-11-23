"""Regression tests for the second review: demo tenancy, login timing, SQL aggregation."""
import statistics

from sqlalchemy import event

from app.core import db as database
from app.models import Approval, Organization, User, Workflow
from app.services import dashboard, seed
from app.core.security import hash_password

from tests.test_review_regressions import client_for


def _second_org_manager(db):
    org = Organization(name="Other Co")
    db.add(org)
    db.flush()
    mgr = User(org_id=org.id, name="Other Manager", email="boss@other.test", role="manager", is_active=True,
               password_hash=hash_password("Other-Pass-12345"))
    db.add(mgr)
    db.commit()
    return org, mgr


def _login(email, password):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, base_url="http://testserver")
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


def test_demo_run_never_creates_data_in_another_organisation(db):
    org_b, _ = _second_org_manager(db)
    other = _login("boss@other.test", "Other-Pass-12345")
    r = other.post("/api/functions/procurement/demo", json={"scenario": "routine"})
    assert r.status_code == 202, r.text
    with database.SessionLocal() as s:
        wf = s.get(Workflow, r.json()["workflow_id"])
        assert wf.org_id == org_b.id
        assert s.get(User, wf.request.requester_id).org_id == org_b.id
        assert all(s.get(Workflow, a.workflow_id).org_id == org_b.id for a in s.query(Approval).filter(Approval.workflow_id == wf.id))
        assert r.json()["requester"] == "Other Manager"  # fell back to the caller, never to the demo org's requester


def test_demo_run_uses_the_demo_requester_of_the_callers_own_org(db):
    r = client_for("manager").post("/api/functions/procurement/demo", json={"scenario": "routine"})
    assert r.status_code == 202
    assert r.json()["requester"]  # org 1 has its own demo requester


def test_login_checks_a_password_hash_even_for_unknown_accounts(db, monkeypatch):
    from app.api import auth
    seen = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda p, h: (seen.append(h), real(p, h))[1])
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": "nobody@nowhere.test", "password": "whatever-1234"}).status_code == 401
    assert len(seen) == 1 and seen[0].startswith("$2")


def test_dashboard_numbers_match_a_straightforward_python_calculation(db):
    seed.seed_history(db)
    completed = db.query(Workflow).filter(Workflow.org_id == 1, Workflow.status == "completed").all()
    human = {a.workflow_id for a in db.query(Approval).filter(Approval.status != "pending")}
    durations = [(w.completed_at - w.started_at).total_seconds() for w in completed if w.completed_at and w.started_at]
    m = dashboard.summary(db, 1)["metrics"]
    assert m["completed_total"] == len(completed)
    assert m["automation_rate"] == round(len([w for w in completed if w.id not in human]) / len(completed) * 100)
    assert m["avg_duration_s"] == round(statistics.mean(durations), 1)
    ex = dashboard.observability(db, 1, {"requests": 0})["workflow_execution"]
    assert ex["completed"] == len(completed)
    assert ex["p95_duration_s"] == round(sorted(durations)[int(len(durations) * 0.95) - 1], 1)
    assert sum(p["completed"] for p in dashboard.summary(db, 1)["throughput"]) <= len(completed)


def test_dashboard_never_loads_workflow_rows_in_bulk(db):
    seed.seed_history(db)
    statements = []
    listener = lambda conn, cur, stmt, *a: statements.append(stmt)  # noqa: E731
    event.listen(database.engine, "before_cursor_execute", listener)
    try:
        dashboard.summary(db, 1)
    finally:
        event.remove(database.engine, "before_cursor_execute", listener)
    full_row_loads = [s for s in statements if "FROM workflows" in s and "workflows.title" in s and "LIMIT" not in s.upper()]
    assert not full_row_loads, full_row_loads


def test_functions_endpoint_uses_a_constant_number_of_queries(db):
    statements = []
    listener = lambda conn, cur, stmt, *a: statements.append(stmt)  # noqa: E731
    admin = client_for("admin")
    event.listen(database.engine, "before_cursor_execute", listener)
    try:
        r = admin.get("/api/functions")
    finally:
        event.remove(database.engine, "before_cursor_execute", listener)
    assert r.status_code == 200 and r.json()
    assert len([s for s in statements if "FROM workflows" in s]) <= 1
