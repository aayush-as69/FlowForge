"""Policy simulator: dry runs that never change anything."""
from app.models import Policy
from app.services import policy_simulator, seed

from tests.test_review_regressions import client_for


def _policy(db, rule_type):
    return db.query(Policy).filter(Policy.org_id == 1, Policy.rule_type == rule_type).one()


def test_no_changes_means_no_difference(db, users):
    seed.seed_history(db)
    r = client_for("admin").post("/api/policies/simulate", json={"sample": 500}).json()
    assert r["mode"] == "history" and r["replayed"] > 10
    assert r["current"] == r["proposed"] and r["changed_count"] == 0


def test_raising_the_auto_limit_reduces_human_workload(db, users):
    seed.seed_history(db)
    p = _policy(db, "auto_execute_limit")
    r = client_for("admin").post("/api/policies/simulate", json={"changes": [{"policy_id": p.id, "params": {"max_amount": 10_000_000}}]}).json()
    assert r["proposed"]["auto"] >= r["current"]["auto"]
    assert r["proposed"]["needs_human"] <= r["current"]["needs_human"]
    assert all(c["before"] != c["after"] for c in r["changed"])
    if r["current"]["needs_human"]:
        assert r["human_workload_change_pct"] >= 0


def test_a_stricter_limit_sends_more_work_to_people(db, users):
    seed.seed_history(db)
    p = _policy(db, "auto_execute_limit")
    r = client_for("admin").post("/api/policies/simulate", json={"changes": [{"policy_id": p.id, "params": {"max_amount": 1}}]}).json()
    assert r["proposed"]["auto"] < r["current"]["auto"] or r["current"]["auto"] == 0
    assert r["proposed"]["needs_human"] >= r["current"]["needs_human"]


def test_simulation_never_writes(db, users):
    seed.seed_history(db)
    p = _policy(db, "auto_execute_limit")
    before = dict(p.params), p.version
    client_for("admin").post("/api/policies/simulate", json={"changes": [{"policy_id": p.id, "params": {"max_amount": 1}, "enabled": False}]})
    db.refresh(p)
    assert (dict(p.params), p.version) == before and p.enabled
    from app.models import AuditEvent
    assert db.query(AuditEvent).filter(AuditEvent.action == "policy.updated").count() == 0


def test_single_purchase_whatif(db, users):
    auto = _policy(db, "auto_execute_limit")
    mgr = db.query(Policy).filter(Policy.key == "approval_manager").one()
    body = {"purchase": {"amount": 85_000, "category": "laptop", "quantity": 1, "budget": 100_000},
            "changes": [{"policy_id": auto.id, "params": {"max_amount": 100_000}},
                        {"policy_id": mgr.id, "params": {"amount": 100_000, "role": "manager"}}]}
    r = client_for("admin").post("/api/policies/simulate", json=body).json()
    assert r["mode"] == "purchase"
    assert r["current"]["outcome"] in ("review", "human") and r["proposed"]["outcome"] == "auto"
    assert r["current"]["reasons"]


def test_invalid_changes_are_rejected_like_real_edits(db, users):
    p = _policy(db, "auto_execute_limit")
    admin = client_for("admin")
    assert admin.post("/api/policies/simulate", json={"changes": [{"policy_id": p.id, "params": {"max_amount": -5}}]}).status_code == 422
    assert admin.post("/api/policies/simulate", json={"changes": [{"policy_id": 999999, "enabled": False}]}).status_code == 422
    assert admin.post("/api/policies/simulate", json={"sample": 5000}).status_code == 422
    assert admin.post("/api/policies/simulate", json={"nonsense": 1}).status_code == 422


def test_only_policy_editors_can_simulate(db, users):
    for role in ("requester", "approver", "manager"):
        assert client_for(role).post("/api/policies/simulate", json={}).status_code == 403


def test_other_organisations_history_is_not_replayed(db, users):
    seed.seed_history(db)
    assert policy_simulator.simulate(db, 999, [])["replayed"] == 0
