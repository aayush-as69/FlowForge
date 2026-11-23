"""Regression tests for the repository-audit findings (metrics growth, chain forks, request guards, ownership)."""
import threading

import pytest
from fastapi.testclient import TestClient

from app.core import db as database
from app.core.config import settings
from app.main import MAX_BODY_BYTES, app
from app.models import ApiMetric, Organization
from app.services import audit

from tests.test_review_regressions import LAPTOP_REQUEST, client_for


def _metric_count() -> int:
    with database.SessionLocal() as s:
        return s.query(ApiMetric).count()


def test_unmatched_and_anonymous_requests_are_not_recorded(db):
    anon = TestClient(app, raise_server_exceptions=False)
    before = _metric_count()
    for i in range(20):
        assert anon.get(f"/api/does-not-exist/{i}").status_code == 404
        assert anon.get("/api/auth/me").status_code == 401
    assert _metric_count() == before
    # an authenticated, matched request is still recorded, with a bounded path
    admin = client_for("admin")
    before = _metric_count()
    assert admin.get("/api/dashboard/summary").status_code == 200
    assert _metric_count() == before + 1
    admin.get("/api/nope/" + "x" * 500)
    assert _metric_count() == before + 1


def test_metrics_are_purged_periodically(db, monkeypatch):
    import app.main as main
    from datetime import timedelta
    with database.SessionLocal() as s:
        s.add(ApiMetric(org_id=1, path="/old", status_code=200, duration_ms=1, ts=database.utcnow() - timedelta(days=400)))
        s.commit()
    monkeypatch.setattr(main, "_PURGE_EVERY", 1)
    client_for("admin").get("/api/dashboard/summary")
    with database.SessionLocal() as s:
        assert s.query(ApiMetric).filter(ApiMetric.path == "/old").count() == 0


@pytest.mark.parametrize("backend", ["sqlite-file", "configured"])
def test_concurrent_audit_writers_do_not_fork_the_chain(tmp_path, backend):
    if backend == "configured" and settings.database_url.startswith("sqlite"):
        pytest.skip("an in-memory SQLite database is a single shared connection; covered by the sqlite-file case")
    database.configure(f"sqlite:///{tmp_path / 'chain.db'}" if backend == "sqlite-file" else settings.database_url)
    try:
        database.Base.metadata.drop_all(database.engine)
        database.init_db()
        with database.SessionLocal() as s:
            s.add(Organization(id=1, name="Acme"))
            s.commit()
        errors: list[Exception] = []

        def writer(n: int):
            try:
                for i in range(8):
                    with database.SessionLocal() as s:
                        audit.record(s, org_id=1, workflow_id=None, actor_type="system", actor=f"w{n}", action=f"t.{n}.{i}")
                        s.commit()
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert not errors, errors
        with database.SessionLocal() as s:
            result = audit.verify_chain(s, 1)
        assert result["checked"] == 48 and result["ok"] and result["forks"] == 0, result
    finally:
        database.configure(settings.database_url)


def test_oversized_bodies_are_refused(db):
    admin = client_for("admin")
    r = admin.post("/api/requests", content=b"x" * (MAX_BODY_BYTES + 10), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_cross_site_state_changes_are_refused(db):
    admin = client_for("admin")
    evil = admin.post("/api/requests", json={"text": LAPTOP_REQUEST}, headers={"origin": "https://evil.example"})
    assert evil.status_code == 403
    assert admin.post("/api/requests", json={"text": LAPTOP_REQUEST}, headers={"origin": "null"}).status_code == 403
    same = admin.post("/api/requests", json={"text": LAPTOP_REQUEST}, headers={"origin": "http://testserver"})
    assert same.status_code == 201
    # reads are never blocked by the origin check
    assert admin.get("/api/auth/me", headers={"origin": "https://evil.example"}).status_code == 200


def test_requesters_cannot_tell_whether_others_requests_exist(db, users):
    from app.services import requests as rs
    req = rs.create_request(db, users["karthik"], text=LAPTOP_REQUEST, fields=None, source="text", demo_faults=[])
    wf = rs.start_workflow(db, req, users["karthik"], step_delay=0)
    mine = client_for("requester")
    missing = mine.get("/api/requests/999999").status_code
    assert mine.get(f"/api/requests/{req.id}").status_code == missing == 404
    assert mine.get(f"/api/workflows/{wf.id}").status_code == 404
