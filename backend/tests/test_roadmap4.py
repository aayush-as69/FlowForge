"""Workflow Builder: validation, versioning, test mode, templates and real execution."""
import copy

from app.models import AuditEvent, Workflow
from app.services import builder
from app.services.builder_templates import TEMPLATES

from tests.test_review_regressions import client_for

SIMPLE = {"steps": [
    {"id": "understand", "type": "extract", "name": "Understand"},
    {"id": "limit", "type": "rule", "name": "Limit", "on_fail": "approval", "message": "Over limit",
     "conditions": [{"field": "amount", "op": "<=", "value": 1000}]},
    {"id": "ok", "type": "approval", "name": "Manager OK", "role": "manager", "when": "flagged"},
    {"id": "tell", "type": "notify", "name": "Tell", "message": "Done: {item}"},
]}
TESTS = [{"name": "small", "fields": {"amount": 500}, "expect": {"outcome": "auto"}},
         {"name": "big", "fields": {"amount": 5000}, "expect": {"outcome": "approval", "role": "manager"}}]


def _published(admin, spec=SIMPLE, tests=TESTS, name="Simple flow"):
    d = admin.post("/api/builder/definitions", json={"name": name, "spec": spec, "tests": tests})
    assert d.status_code == 201, d.text
    p = admin.post(f"/api/builder/definitions/{d.json()['id']}/publish")
    assert p.status_code == 200, p.text
    return p.json()


def test_every_template_is_valid_and_passes_its_own_tests():
    assert len(TEMPLATES) >= 5
    for t in TEMPLATES:
        assert builder.validate_spec(t["spec"]) == [] and builder.validate_tests(t["tests"]) == []
        r = builder.run_tests(t["spec"], t["tests"])
        assert r["failed"] == 0 and r["total"] >= 2, (t["key"], r)


def test_validation_reports_every_problem():
    bad = {"steps": [{"id": "A", "type": "rule", "name": "x", "conditions": [{"field": "nope", "op": "<", "value": "a"}], "on_fail": "x"},
                     {"id": "b", "type": "approval", "name": "y", "role": "king", "when": "flagged"},
                     {"id": "b", "type": "teleport", "name": "z"}]}
    problems = builder.validate_spec(bad)
    text = " | ".join(problems)
    for needle in ("id must be lowercase", "unknown field", "on_fail", "role must be", "unknown type"):
        assert needle in text, (needle, problems)
    assert builder.validate_spec({"steps": []}) and builder.validate_spec("x") and builder.validate_spec({"steps": [{"id": "a", "type": "notify", "name": "n", "message": "m"}]})
    assert builder.validate_spec({"steps": [SIMPLE["steps"][0], {**SIMPLE["steps"][0], "id": "two"}]})


def test_missing_values_never_pass_a_rule(db, users):
    r = builder.dry_run(SIMPLE, fields={"item": "x"})
    assert r["outcome"] == "approval"  # no amount → cannot verify → flagged, not auto-approved


def test_dry_run_trace_and_notify_text(db, users):
    r = builder.dry_run(SIMPLE, text="Need 3 monitors for 800 rupees")
    assert r["outcome"] in ("auto", "approval")
    r = builder.dry_run(SIMPLE, fields={"amount": 10, "item": "pens"})
    assert r["outcome"] == "auto" and r["trace"][-1]["detail"] == "Done: pens"


def test_only_admins_edit_but_staff_can_read_and_test(db, users):
    admin, mgr, req = client_for("admin"), client_for("manager"), client_for("requester")
    assert mgr.post("/api/builder/definitions", json={"name": "Nope flow"}).status_code == 403
    d = admin.post("/api/builder/definitions", json={"name": "Alpha flow", "template_key": "expense-approval"}).json()
    assert req.get("/api/builder/definitions").status_code == 200
    assert req.put(f"/api/builder/definitions/{d['id']}", json={"name": "Hax"}).status_code == 403
    t = mgr.post("/api/builder/test", json={"spec": d["spec"], "fields": {"amount": 90000}}).json()
    assert t["outcome"] == "approval" and t["role"] == "manager"
    assert mgr.post("/api/builder/test", json={"spec": {"steps": []}, "text": "x"}).status_code == 422
    assert mgr.post("/api/builder/test", json={"spec": d["spec"]}).status_code == 422


def test_publish_requires_passing_tests(db, users):
    admin = client_for("admin")
    none = admin.post("/api/builder/definitions", json={"name": "No tests", "spec": SIMPLE}).json()
    assert admin.post(f"/api/builder/definitions/{none['id']}/publish").status_code == 422
    wrong = admin.post("/api/builder/definitions", json={"name": "Wrong test", "spec": SIMPLE,
                                                         "tests": [{"name": "t", "fields": {"amount": 5}, "expect": {"outcome": "blocked"}}]}).json()
    r = admin.post(f"/api/builder/definitions/{wrong['id']}/publish")
    assert r.status_code == 422 and "expected blocked" in r.text


def test_versions_are_immutable_once_published(db, users):
    admin = client_for("admin")
    v1 = _published(admin)
    assert admin.put(f"/api/builder/definitions/{v1['id']}", json={"name": "changed"}).status_code == 409
    v2 = admin.post(f"/api/builder/definitions/{v1['id']}/new-version").json()
    assert v2["version"] == 2 and v2["status"] == "draft" and v2["spec"] == v1["spec"]
    assert admin.post(f"/api/builder/definitions/{v1['id']}/new-version").status_code == 409  # one draft at a time
    spec2 = copy.deepcopy(SIMPLE)
    spec2["steps"][1]["conditions"][0]["value"] = 100
    assert admin.put(f"/api/builder/definitions/{v2['id']}", json={"spec": spec2}).status_code == 200
    assert admin.post(f"/api/builder/definitions/{v2['id']}/publish").status_code == 422  # test "small" (500) now fails
    admin.put(f"/api/builder/definitions/{v2['id']}", json={"tests": [{"name": "t", "fields": {"amount": 500}, "expect": {"outcome": "approval", "role": "manager"}}]})
    assert admin.post(f"/api/builder/definitions/{v2['id']}/publish").status_code == 200
    items = admin.get("/api/builder/definitions").json()["items"]
    row = next(i for i in items if i["key"] == v1["key"])
    assert [v["status"] for v in row["versions"]] == ["published", "archived"] and row["version"] == 2


def test_running_work_stays_on_the_version_it_started_with(db, users):
    admin, mgr = client_for("admin"), client_for("manager")
    v1 = _published(admin)
    wf = mgr.post(f"/api/builder/definitions/{v1['id']}/run", json={"fields": {"amount": 5000, "item": "chairs"}}).json()
    assert mgr.get(f"/api/workflows/{wf['id']}").json()["status"] == "waiting_human"
    v2 = admin.post(f"/api/builder/definitions/{v1['id']}/new-version").json()
    spec2 = copy.deepcopy(SIMPLE)
    spec2["steps"].append({"id": "extra", "type": "notify", "name": "Extra", "message": "new"})
    admin.put(f"/api/builder/definitions/{v2['id']}", json={"spec": spec2})
    assert admin.post(f"/api/builder/definitions/{v2['id']}/publish").status_code == 200
    # the old definition is archived, but the in-flight workflow still resolves and finishes on v1's steps
    assert mgr.post(f"/api/builder/definitions/{v1['id']}/run", json={"text": "x"}).status_code == 409
    a = admin.get("/api/approvals").json()["items"][0]
    assert admin.post(f"/api/approvals/{a['id']}/decision", json={"action": "approve", "note": "fine"}).status_code == 200
    done = admin.get(f"/api/workflows/{wf['id']}").json()
    assert done["status"] == "completed" and [s["key"] for s in done["steps"]] == ["understand", "limit", "ok", "tell"]


def test_running_a_published_workflow_end_to_end(db, users):
    admin, mgr, req = client_for("admin"), client_for("manager"), client_for("requester")
    d = _published(admin)
    assert req.post(f"/api/builder/definitions/{d['id']}/run", json={"text": "x"}).status_code == 403
    assert mgr.post(f"/api/builder/definitions/{d['id']}/run", json={}).status_code == 422
    auto = mgr.post(f"/api/builder/definitions/{d['id']}/run", json={"fields": {"amount": 200, "item": "pens"}}).json()
    detail = mgr.get(f"/api/workflows/{auto['id']}").json()
    assert detail["status"] == "completed" and detail["outcome"].startswith("Completed 'Simple flow'")
    assert detail["context"]["input"]["fields"] == {"amount": 200, "item": "pens"} and detail["context"]["definition"]["version"] == 1
    assert [s["status"] for s in detail["steps"]] == ["completed", "completed", "skipped", "completed"]
    held = mgr.post(f"/api/builder/definitions/{d['id']}/run", json={"fields": {"amount": 9000}}).json()
    assert mgr.get(f"/api/workflows/{held['id']}").json()["status"] == "waiting_human"
    a = admin.get("/api/approvals").json()["items"][0]
    assert a["can_decide"] is True
    # the person who started the workflow cannot approve it, even with the role to do so
    me = mgr.get("/api/approvals").json()["items"][0]
    assert me["can_decide"] is False
    r = mgr.post(f"/api/approvals/{a['id']}/decision", json={"action": "approve", "note": "mine"})
    assert r.status_code == 403
    assert admin.post(f"/api/approvals/{a['id']}/decision", json={"action": "approve", "note": "ok"}).status_code == 200
    assert mgr.get(f"/api/workflows/{held['id']}").json()["status"] == "completed"
    assert db.query(AuditEvent).filter(AuditEvent.action == "notification.recorded").count() == 2


def test_rejecting_stops_the_workflow(db, users):
    admin, mgr = client_for("admin"), client_for("manager")
    d = _published(admin)
    held = mgr.post(f"/api/builder/definitions/{d['id']}/run", json={"fields": {"amount": 9000}}).json()
    a = admin.get("/api/approvals").json()["items"][0]
    assert admin.post(f"/api/approvals/{a['id']}/decision", json={"action": "reject", "note": "no"}).status_code == 200
    assert mgr.get(f"/api/workflows/{held['id']}").json()["status"] in ("cancelled", "failed")


def test_blocking_rule_goes_to_review_and_can_be_waived(db, users):
    admin, mgr = client_for("admin"), client_for("manager")
    tpl = next(t for t in TEMPLATES if t["key"] == "purchase-order-approval")
    d = _published(admin, tpl["spec"], tpl["tests"], "PO flow")
    wf = mgr.post(f"/api/builder/definitions/{d['id']}/run", json={"fields": {"category": "vehicles", "amount": 5000}}).json()
    detail = mgr.get(f"/api/workflows/{wf['id']}").json()
    assert detail["status"] == "waiting_human" and detail["exceptions"][0]["code"] == "RULE_BLOCKED"
    a = admin.get("/api/approvals").json()["items"][0]
    assert a["kind"] == "exception_review"
    assert admin.post(f"/api/approvals/{a['id']}/decision", json={"action": "approve", "note": "exception granted"}).status_code == 200
    after = mgr.get(f"/api/workflows/{wf['id']}").json()
    assert after["status"] == "waiting_human"  # the waived rule passed; now the normal approver review is requested
    assert [s["status"] for s in after["steps"]][:2] == ["completed", "resolved"]


def test_existing_pages_cope_with_workflows_that_have_no_request(db, users):
    admin, mgr = client_for("admin"), client_for("manager")
    d = _published(admin)
    wf = mgr.post(f"/api/builder/definitions/{d['id']}/run", json={"fields": {"amount": 9000}}).json()
    for path in (f"/api/workflows/{wf['id']}", f"/api/workflows/{wf['id']}/explanation", f"/api/workflows/{wf['id']}/cost",
                 "/api/action-center", "/api/analytics/overview", "/api/dashboard/summary", "/api/workflows", "/api/approvals"):
        r = mgr.get(path)
        assert r.status_code == 200, (path, r.status_code, r.text[:200])


def test_other_organisations_cannot_see_or_run_definitions(db, users):
    from app.models import Organization
    from tests.test_review_regressions import add_user

    org = Organization(name="Other")
    db.add(org)
    db.commit()
    add_user(db, org_id=org.id, email="x@other.test", role="admin")
    admin = client_for("admin")
    d = _published(admin)
    other = client_for("x@other.test", "pw-for-tests")
    assert other.get(f"/api/builder/definitions/{d['id']}").status_code == 404
    assert other.post(f"/api/builder/definitions/{d['id']}/run", json={"text": "x"}).status_code == 404
    assert other.get("/api/builder/definitions").json()["items"] == []
    assert db.query(Workflow).count() == 0
