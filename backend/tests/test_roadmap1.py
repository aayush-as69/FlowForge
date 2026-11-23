"""Explainability and Action Center."""
from app.core import db as database
from app.models import Organization, User
from app.services import requests as rs
from app.workflows import engine as wf_engine

from tests.test_review_regressions import LAPTOP_REQUEST, client_for

ROUTINE = "Need 5 wireless keyboard and mouse sets for the support team. Budget ₹20,000. Needed by next Friday."


def _run(db, users, text, who="requester"):
    req = rs.create_request(db, users[who], text=text, fields=None, source="text", demo_faults=[])
    wf = rs.start_workflow(db, req, users[who], step_delay=0)
    wf_engine.run(db, wf.id)
    return wf


def test_explanation_of_an_autonomous_workflow(db, users):
    wf = _run(db, users, ROUTINE)
    exp = client_for("admin").get(f"/api/workflows/{wf.id}/explanation").json()
    assert exp["status"] == "completed" and "without human involvement" in exp["headline"]
    assert exp["policy"]["passed"] and all(r["label"] for r in exp["policy"]["results"])
    assert exp["autonomy"]["level"] == 1 and exp["human"] == []
    v = exp["vendor"]
    assert v["selected"] and v["reasons"][0]["text"].startswith(("Highest overall score", "Only eligible"))
    assert any(r["text"] == "Approved vendor" and r["ok"] for r in v["reasons"])
    assert all(r["vendor"] != v["selected"] for r in v["rejected"])


def test_explanation_of_a_workflow_waiting_for_a_person(db, users):
    wf = _run(db, users, LAPTOP_REQUEST)
    exp = client_for("admin").get(f"/api/workflows/{wf.id}/explanation").json()
    assert exp["status"] == "waiting_human"
    assert "Waiting for a person" in exp["headline"]
    assert exp["exceptions"] or exp["autonomy"]


def test_explanation_respects_visibility(db, users):
    wf = _run(db, users, ROUTINE, who="karthik")
    assert client_for("requester").get(f"/api/workflows/{wf.id}/explanation").status_code == 404  # someone else's request
    assert client_for("requester").get("/api/workflows/999999/explanation").status_code == 404


def test_action_center_lists_what_needs_a_person_and_hides_it_from_requesters(db, users):
    _run(db, users, LAPTOP_REQUEST)
    mgr = client_for("manager").get("/api/action-center").json()
    assert mgr["counts"]["approvals"] + mgr["counts"]["exceptions"] >= 1
    assert all({"type", "workflow_id", "age_hours", "overdue", "mine"} <= set(i) for i in mgr["items"])
    assert mgr["items"] == sorted(mgr["items"], key=lambda i: (not i["overdue"], not i["mine"], -i["age_hours"]))
    req = client_for("requester").get("/api/action-center").json()
    assert req["items"] == [] and req["counts"]["mine"] == 0


def test_action_center_never_shows_another_organisations_items(db, users):
    _run(db, users, LAPTOP_REQUEST)
    org = Organization(name="Other")
    db.add(org)
    db.flush()
    from app.core.security import hash_password
    db.add(User(org_id=org.id, name="Other Mgr", email="m@other.test", role="manager", is_active=True,
                password_hash=hash_password("Other-Pass-12345")))
    db.commit()
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": "m@other.test", "password": "Other-Pass-12345"}).status_code == 200
    assert c.get("/api/action-center").json()["items"] == []
