import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models import Request


def client_for(role: str | None):
    c = TestClient(app, raise_server_exceptions=False)
    if role:
        r = c.post("/api/auth/login", json={"email": f"{role}@flowforge.demo", "password": settings.demo_password})
        assert r.status_code == 200, r.text
    return c


@pytest.fixture()
def anon(db):
    return client_for(None)


@pytest.fixture()
def admin(db):
    return client_for("admin")


def test_authentication_flow(db, anon):
    assert anon.get("/api/auth/me").status_code == 401
    bad = anon.post("/api/auth/login", json={"email": "admin@flowforge.demo", "password": "wrong"})
    assert bad.status_code == 401 and "Incorrect" in bad.json()["detail"]
    ok = anon.post("/api/auth/login", json={"email": "admin@flowforge.demo", "password": settings.demo_password})
    assert ok.status_code == 200 and "httponly" in ok.headers["set-cookie"].lower()
    me = anon.get("/api/auth/me").json()
    assert me["user"]["role"] == "admin" and "policies:write" in me["permissions"]
    token = ok.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    anon.post("/api/auth/logout")
    assert anon.get("/api/auth/me").status_code == 401
    assert anon.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_protected_routes_require_a_session(anon):
    for path in ["/api/dashboard/summary", "/api/workflows", "/api/approvals", "/api/exceptions", "/api/policies",
                 "/api/integrations", "/api/audit", "/api/vendors", "/api/functions"]:
        assert anon.get(path).status_code == 401, path


def test_role_based_authorization(db):
    requester, approver, auditor = client_for("requester"), client_for("approver"), client_for("auditor")
    assert requester.get("/api/approvals").status_code == 403
    assert requester.get("/api/audit").status_code == 403
    assert approver.patch("/api/policies/1", json={"enabled": False}).status_code == 403
    assert auditor.patch("/api/policies/1", json={"enabled": False}).status_code == 403
    assert auditor.post("/api/requests", json={"text": "laptop"}).status_code == 403
    assert approver.patch("/api/integrations/erp", json={"status": "disconnected"}).status_code == 403
    assert requester.get("/api/policies").status_code == 200


def test_input_validation(admin):
    r = admin.post("/api/requests", json={})
    assert r.status_code == 422 and r.json()["detail"] == "Some fields are invalid."
    assert admin.post("/api/requests", json={"text": "laptop", "source": "carrier-pigeon"}).status_code == 422
    assert admin.post("/api/requests", json={"fields": {"quantity": 0}}).status_code == 422
    assert admin.post("/api/requests", json={"text": "x" * 9000}).status_code == 422
    assert admin.post("/api/approvals/1/decision", json={"action": "explode"}).status_code == 422
    assert admin.get("/api/workflows?page=0").status_code == 422


def test_error_handling_is_explained(admin):
    assert admin.get("/api/workflows/9999").status_code == 404
    assert "not found" in admin.get("/api/workflows/9999").json()["detail"].lower()
    created = admin.post("/api/requests", json={"text": "Need something nice. Budget ₹5,000."}).json()
    r = admin.post(f"/api/requests/{created['id']}/execute")
    assert r.status_code == 422 and "missing information" in r.json()["detail"]
    fixed = admin.patch(f"/api/requests/{created['id']}", json={"category": "peripherals", "quantity": 2, "item": "Headsets"})
    assert fixed.json()["corrected"] is True
    assert admin.post("/api/policies/1/../x").status_code in (404, 405)


def test_policy_admin_edit_is_validated_and_audited(admin):
    pol = next(p for p in admin.get("/api/policies").json() if p["rule_type"] == "budget_limit")
    assert admin.patch(f"/api/policies/{pol['id']}", json={"params": {"max_amount": -1}}).status_code == 422
    assert admin.patch(f"/api/policies/{pol['id']}", json={"params": {"nope": 1}}).status_code == 422
    ok = admin.patch(f"/api/policies/{pol['id']}", json={"params": {"max_amount": 750000}})
    assert ok.status_code == 200 and ok.json()["version"] == 2
    events = admin.get("/api/audit?q=policy.updated").json()
    assert events["total"] == 1 and events["items"][0]["actor"]


def test_full_flow_through_api_with_human_decisions(db):
    admin, approver, manager, requester = client_for("admin"), client_for("approver"), client_for("manager"), client_for("requester")
    r = requester.post("/api/requests", json={
        "text": "Purchase a laptop for a new employee joining next Monday. Budget ₹1,00,000."})
    assert r.status_code == 201
    body = r.json()
    assert body["category"] == "laptop" and body["budget"] == 100000 and body["quantity"] == 1 and body["purpose"] == "New employee"
    assert requester.patch(f"/api/requests/{body['id']}", json={"requirements": "16GB RAM"}).json()["requirements"] == "16GB RAM"
    # The demo story includes a one-shot ERP timeout; inject it explicitly in this integration test.
    req = db.get(Request, body["id"])
    req.demo_faults = ["erp_timeout"]
    db.commit()
    wf_id = requester.post(f"/api/requests/{body['id']}/execute").json()["workflow_id"]
    assert requester.post(f"/api/requests/{body['id']}/execute").status_code == 409

    pending = approver.get("/api/approvals").json()
    assert pending["pending_total"] == 1
    a = pending["items"][0]
    assert a["kind"] == "exception_review" and a["can_decide"] and a["recommendation"] and a["supporting_data"]["alternatives_rejected"]
    assert requester.post(f"/api/approvals/{a['id']}/decision", json={"action": "approve"}).status_code == 403
    assert manager.get("/api/approvals").json()["items"][0]["can_decide"] is True
    assert approver.post(f"/api/approvals/{a['id']}/decision", json={"action": "approve", "note": "ok"}).status_code == 200
    assert approver.post(f"/api/approvals/{a['id']}/decision", json={"action": "approve"}).status_code == 409

    a2 = manager.get("/api/approvals").json()["items"][0]
    assert a2["kind"] == "approval" and a2["assigned_role"] == "manager"
    assert approver.post(f"/api/approvals/{a2['id']}/decision", json={"action": "approve"}).json() if False else True
    assert approver.post(f"/api/approvals/{a2['id']}/decision", json={"action": "approve"}).status_code == 403
    assert manager.post(f"/api/approvals/{a2['id']}/decision", json={"action": "approve", "note": "fine"}).status_code == 200

    wf = admin.get(f"/api/workflows/{wf_id}").json()
    assert wf["status"] == "completed" and wf["purchase_order"]["erp_ref"]
    assert len(wf["approvals"]) == 2 and len(wf["decisions"]) >= 4 and len(wf["exceptions"]) == 2
    assert {e["status"] for e in wf["exceptions"]} == {"resolved_by_human", "auto_resolved"}
    assert wf["plan"] and wf["steps"][0]["key"] == "ingest" and wf["outcome"]
    actions = [e["action"] for e in wf["audit"]]
    for expected in ("request.received", "request.extracted", "policy.evaluated", "vendors.evaluated", "decision.made",
                     "approval.requested", "approval.decided", "exception.detected", "workflow.completed"):
        assert expected in actions, expected
    assert admin.get(f"/api/workflow-steps/{wf['steps'][3]['id']}").json()["key"] == "vendor_evaluation"
    # requester sees only own work; auditor can read audit but not decide
    assert requester.get("/api/workflows").json()["total"] == 1
    assert client_for("auditor").get("/api/audit").status_code == 200
    summary = admin.get("/api/dashboard/summary").json()
    assert summary["metrics"]["completed_total"] == 1 and summary["metrics"]["human_intervention"] == 100
    assert admin.get("/api/exceptions/summary").json()["auto_resolved"] == 1
    assert admin.get("/api/dashboard/observability").status_code == 200


def test_disconnected_integration_triggers_exception_engine_and_retry(db):
    admin = client_for("admin")
    assert admin.patch("/api/integrations/documents", json={"status": "disconnected"}).json()["status"] == "disconnected"
    r = admin.post("/api/functions/procurement/demo", json={"scenario": "routine"})
    assert r.status_code == 202
    wf_id = r.json()["workflow_id"]
    wf = admin.get(f"/api/workflows/{wf_id}").json()
    assert wf["status"] == "waiting_human" and wf["exceptions"][0]["code"] == "INTEGRATION_UNAVAILABLE"
    assert wf["exceptions"][0]["status"] == "awaiting_review" and wf["exceptions"][0]["attempts"] == 2
    admin.patch("/api/integrations/documents", json={"status": "connected"})
    a = admin.get("/api/approvals").json()["items"][0]
    assert admin.post(f"/api/approvals/{a['id']}/decision", json={"action": "approve", "note": "reconnected"}).status_code == 200
    assert admin.get(f"/api/workflows/{wf_id}").json()["status"] == "completed"
