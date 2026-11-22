"""Regression tests for the code-review findings:

1. cross-tenant access to approvals / exceptions / dashboards / integrations
2. 'Modify' decisions that pick an ineligible vendor were accepted, then silently ignored
3. a non-numeric vendor_id in a modification caused HTTP 500
4. an admin could approve their own request (separation of duties)
5. the login throttle could be bypassed with whitespace/case variants of the e-mail
(6, the open redirect on the login page, is covered by src/lib/safe-redirect.test.mjs)
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import hash_password
from app.main import app
from app.models import (Approval, BusinessFunction, Integration, Organization, PurchaseOrder, User, Vendor, Workflow,
                        WorkflowException)
from app.services import approvals
from app.services import requests as rs
from app.workflows import engine

NETWORK_REQUEST = ("Purchase 4 network switches for the Pune office. Budget ₹3,80,000. Required by next Friday. "
                   "Purpose: team expansion")
LAPTOP_REQUEST = "Purchase a laptop for a new employee joining next Monday. Budget ₹1,00,000."


def client_for(who: str, password: str | None = None, host: str | None = None) -> TestClient:
    kwargs = {"client": (host, 50000)} if host else {}
    c = TestClient(app, raise_server_exceptions=False, **kwargs)
    email = who if "@" in who else f"{who}@flowforge.demo"
    r = c.post("/api/auth/login", json={"email": email, "password": password or settings.demo_password})
    assert r.status_code == 200, r.text
    return c


def add_user(db, *, org_id: int, email: str, role: str, password: str = "pw-for-tests") -> str:
    db.add(User(org_id=org_id, email=email, name=email.split("@")[0].title(), role=role,
                password_hash=hash_password(password), is_active=True))
    db.commit()
    return password


def vendor_ids(db) -> dict[str, int]:
    return {v.name: v.id for v in db.query(Vendor).all()}


def start_primary_demo(admin) -> int:
    """Laptop scenario: Bluepeak is 18% above its historical average -> price-anomaly review for an approver."""
    r = admin.post("/api/functions/procurement/demo", json={"scenario": "laptop_primary"})
    assert r.status_code == 202, r.text
    return r.json()["workflow_id"]


def pending_approval(client) -> dict:
    items = client.get("/api/approvals").json()["items"]
    assert items, "expected a pending approval"
    return items[0]


def decide(client, approval_id: int, action: str, note: str = "reviewed", modification=None):
    body = {"action": action, "note": note}
    if modification is not None:
        body["modification"] = modification
    return client.post(f"/api/approvals/{approval_id}/decision", json=body)


# --------------------------------------------------------------------------------------------------
# 1. tenant isolation
# --------------------------------------------------------------------------------------------------
def test_other_tenant_cannot_read_or_decide_anything_in_this_org(db):
    admin = client_for("admin")
    wid = start_primary_demo(admin)
    approval = pending_approval(admin)
    exception_id = admin.get("/api/exceptions").json()["items"][0]["id"]

    org2 = Organization(name="Other Tenant Ltd")
    db.add(org2)
    db.flush()
    db.add(BusinessFunction(org_id=org2.id, key="procurement", name="Procurement", description="x", status="active"))
    pw = add_user(db, org_id=org2.id, email="boss@other.example", role="admin")
    outsider = client_for("boss@other.example", pw)

    # approvals: read + decide are 404, and nothing about the workflow changes
    assert outsider.get(f"/api/approvals/{approval['id']}").status_code == 404
    assert decide(outsider, approval["id"], "approve", "from another tenant").status_code == 404
    listing = outsider.get("/api/approvals").json()
    assert listing["total"] == 0 and listing["pending_total"] == 0
    db.expire_all()
    assert db.get(Approval, approval["id"]).status == "pending"
    assert (db.get(Workflow, wid).context or {}).get("overrides") == {}

    # exceptions
    assert outsider.get(f"/api/exceptions/{exception_id}").status_code == 404
    assert sum(outsider.get("/api/exceptions/summary").json().values()) == 0
    assert outsider.get("/api/exceptions").json()["total"] == 0

    # dashboards must not count the other organisation's data
    metrics = outsider.get("/api/dashboard/summary").json()
    assert metrics["metrics"]["pending_review"] == 0 and metrics["metrics"]["open_exceptions"] == 0
    assert metrics["exception_counts"] == {}
    obs = outsider.get("/api/dashboard/observability").json()
    assert obs["exceptions"]["total"] == 0 and obs["human_interventions"] == 0 and obs["tool_calls"] == {}

    # function statistics are per organisation
    functions = outsider.get("/api/functions").json()
    assert functions[0]["stats"] == {"total": 0, "active": 0, "completed": 0}

    # integrations belong to an organisation too
    assert outsider.patch("/api/integrations/erp", json={"status": "disconnected"}).status_code == 404
    assert outsider.post("/api/integrations/erp/check").status_code == 404
    assert db.query(Integration).filter_by(key="erp").one().status == "connected"

    # control: the owning organisation still sees everything
    assert admin.get(f"/api/approvals/{approval['id']}").status_code == 200
    assert admin.get(f"/api/exceptions/{exception_id}").status_code == 200
    assert admin.get("/api/dashboard/summary").json()["metrics"]["pending_review"] == 1


# --------------------------------------------------------------------------------------------------
# 2. 'Modify' must either do what the human chose or be refused - never silently do something else
# --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("vendor", ["Dealzone Traders", "Everline Computers", "nobody"])
def test_modify_on_exception_review_rejects_ineligible_or_unknown_vendor(db, vendor):
    """Dealzone is not approved, Everline is unavailable, 9999 does not exist."""
    admin, approver = client_for("admin"), client_for("approver")
    wid = start_primary_demo(admin)
    approval = pending_approval(approver)
    assert approval["kind"] == "exception_review"
    vid = 9999 if vendor == "nobody" else vendor_ids(db)[vendor]

    r = decide(approver, approval["id"], "modify", modification={"vendor_id": vid})

    assert r.status_code == 422, r.text
    db.expire_all()
    assert db.get(Approval, approval["id"]).status == "pending"
    wf = db.get(Workflow, wid)
    assert wf.status == "waiting_human" and (wf.context or {}).get("overrides") == {}


def test_modify_to_an_eligible_vendor_is_honoured(db):
    admin, approver, manager = client_for("admin"), client_for("approver"), client_for("manager")
    wid = start_primary_demo(admin)
    first = pending_approval(approver)
    apex = vendor_ids(db)["Apex Technologies"]

    assert decide(approver, first["id"], "modify", modification={"vendor_id": apex}).status_code == 200
    second = pending_approval(manager)
    assert second["kind"] == "approval"
    assert decide(manager, second["id"], "approve").status_code == 200

    db.expire_all()
    assert db.get(Workflow, wid).status == "completed"
    po = db.query(PurchaseOrder).filter_by(workflow_id=wid).one()
    assert po.vendor.name == "Apex Technologies"  # the vendor the human picked, not the top-ranked one


def test_modify_at_the_approval_step_rejects_a_vendor_that_cannot_fulfil(db):
    admin, approver, manager = client_for("admin"), client_for("approver"), client_for("manager")
    start_primary_demo(admin)
    assert decide(approver, pending_approval(approver)["id"], "approve").status_code == 200
    approval = pending_approval(manager)
    assert approval["kind"] == "approval"

    # Everline is approved and sells laptops, but is currently unavailable
    r = decide(manager, approval["id"], "modify", modification={"vendor_id": vendor_ids(db)["Everline Computers"]})

    assert r.status_code == 422, r.text
    db.expire_all()
    assert db.get(Approval, approval["id"]).status == "pending"


def test_engine_never_silently_replaces_a_forced_vendor_that_is_ineligible(db, users):
    """Defence in depth: even if a bad override reaches the engine it must raise, not fall back to rank #1."""
    req = rs.create_request(db, users["requester"], text=LAPTOP_REQUEST, fields=None, source="text")
    wf = rs.start_workflow(db, req, users["requester"], step_delay=0)
    everline = vendor_ids(db)["Everline Computers"]  # unavailable
    wf.context = {**(wf.context or {}), "overrides": {"forced_vendor_id": everline}}
    db.commit()

    engine.run(db, wf.id)
    db.refresh(wf)

    assert wf.status == "waiting_human"
    codes = [e.code for e in db.query(WorkflowException).filter_by(workflow_id=wf.id)]
    assert codes == ["FORCED_VENDOR_INELIGIBLE"]
    assert "selected" not in (wf.context or {})

    # a human can acknowledge it; the workflow then continues with normal vendor selection
    approval = db.query(Approval).filter_by(workflow_id=wf.id, status="pending").one()
    assert approvals.decide(db, approval, users["approver"], "approve", "use the normal ranking", None) is True
    engine.run(db, wf.id)
    db.refresh(wf)
    assert (wf.context or {}).get("overrides", {}).get("forced_vendor_id") is None
    assert wf.status == "waiting_human"  # now the genuine price anomaly review
    assert "PRICE_ANOMALY" in {e.code for e in db.query(WorkflowException).filter_by(workflow_id=wf.id)}


# --------------------------------------------------------------------------------------------------
# 3. malformed modification payloads are a client error, not a crash
# --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["abc", "2", 1.5, True, -3, 0, None, [1], {"id": 1}])
def test_vendor_id_must_be_a_positive_integer(db, bad):
    admin, approver = client_for("admin"), client_for("approver")
    start_primary_demo(admin)
    approval = pending_approval(approver)

    r = decide(approver, approval["id"], "modify", modification={"vendor_id": bad})

    assert r.status_code == 422, (bad, r.status_code, r.text)
    db.expire_all()
    assert db.get(Approval, approval["id"]).status == "pending"


def test_modification_may_only_contain_vendor_id(db):
    admin, approver = client_for("admin"), client_for("approver")
    start_primary_demo(admin)
    r = decide(approver, pending_approval(approver)["id"], "modify", modification={"vendor_id": 1, "total": 1})
    assert r.status_code == 422


# --------------------------------------------------------------------------------------------------
# 4. separation of duties applies to admins too
# --------------------------------------------------------------------------------------------------
def test_admin_cannot_decide_their_own_request_but_another_admin_can(db):
    admin = client_for("admin")
    request_id = admin.post("/api/requests", json={"text": NETWORK_REQUEST}).json()["id"]
    wid = admin.post(f"/api/requests/{request_id}/execute").json()["workflow_id"]
    approval = pending_approval(admin)
    assert approval["assigned_role"] == "admin" and approval["level"] == 3

    assert approval["can_decide"] is False and "Separation of duties" in approval["cannot_decide_reason"]
    r = decide(admin, approval["id"], "approve", "approving my own purchase")
    assert r.status_code == 403 and "Separation of duties" in r.json()["detail"]
    assert decide(admin, approval["id"], "reject", "rejecting my own purchase").status_code == 403
    db.expire_all()
    assert db.get(Approval, approval["id"]).status == "pending"
    assert db.get(Workflow, wid).status == "waiting_human"

    # a different administrator can take the decision
    org_id = db.query(User).filter_by(email="admin@flowforge.demo").one().org_id
    pw = add_user(db, org_id=org_id, email="admin2@flowforge.demo", role="admin")
    second = client_for("admin2@flowforge.demo", pw)
    assert decide(second, approval["id"], "approve", "reviewed independently").status_code == 200
    db.expire_all()
    assert db.get(Workflow, wid).status == "completed"


def test_manager_still_cannot_decide_their_own_request(db):
    manager = client_for("manager")
    request_id = manager.post("/api/requests", json={
        "text": "Need 4 27-inch monitors for the platform team. Budget ₹1,40,000. Required by next Thursday."}).json()["id"]
    manager.post(f"/api/requests/{request_id}/execute")
    approval = pending_approval(manager)
    assert decide(manager, approval["id"], "approve").status_code == 403


# --------------------------------------------------------------------------------------------------
# 5. login throttling
# --------------------------------------------------------------------------------------------------
def login(c: TestClient, email: str, password: str):
    return c.post("/api/auth/login", json={"email": email, "password": password}).status_code


def test_throttle_treats_case_and_whitespace_variants_as_the_same_account(db):
    c = TestClient(app, raise_server_exceptions=False)
    variants = ["admin@flowforge.demo", " admin@flowforge.demo", "ADMIN@flowforge.demo ", "admin@flowforge.demo\t",
                "  Admin@Flowforge.Demo  ", "admin@flowforge.demo ", " admin@flowforge.demo", "admin@flowforge.demo"]
    assert [login(c, v, "wrong-password") for v in variants] == [401] * 8

    # the account is now throttled for every spelling - even with the right password
    for v in ("admin@flowforge.demo", " admin@flowforge.demo ", "ADMIN@FLOWFORGE.DEMO"):
        assert login(c, v, settings.demo_password) == 429, v


def test_variant_spellings_still_log_in_normally(db):
    c = TestClient(app, raise_server_exceptions=False)
    assert login(c, "  ADMIN@flowforge.demo ", settings.demo_password) == 200
    assert c.get("/api/auth/me").json()["user"]["email"] == "admin@flowforge.demo"


def test_throttle_limits_password_spraying_from_one_address(db):
    spray = TestClient(app, raise_server_exceptions=False, client=("198.51.100.7", 4000))
    codes = [login(spray, f"user{i}@nowhere.example", "guess") for i in range(60)]
    assert codes[0] == 401 and 429 in codes
    assert codes.index(429) <= 45  # cut off after a bounded number of failures, not after 60 free guesses

    # other addresses are unaffected, and successful logins never count against the address limit
    other = TestClient(app, raise_server_exceptions=False, client=("203.0.113.9", 4000))
    assert [login(other, "manager@flowforge.demo", settings.demo_password) for _ in range(50)] == [200] * 50
