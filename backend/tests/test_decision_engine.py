from types import SimpleNamespace as NS

from app.decisions.engine import DecisionConfig, decide
from app.services.policy_engine import PolicyReport, PolicyResult

CFG = DecisionConfig()


def report(role=None, status="pass", sev="block"):
    r = PolicyReport()
    if role:
        r.results.append(PolicyResult("a", "Approval", "approval", "warn", "needs approval", "warn", role))
    if status == "fail":
        r.results.append(PolicyResult("b", "Block", "category", "fail", "blocked", sev))
    return r


def facts(**kw):
    return {"amount": 20_000, "budget": 30_000, "vendor_approved": True, "price_delta_pct": 2.0, **kw}


def test_level1_auto_execute():
    d = decide(facts(), report(), CFG)
    assert d.level == 1 and d.outcome == "auto_execute" and not d.needs_human


def test_level2_review_for_price_anomaly():
    d = decide(facts(price_delta_pct=18.0), report(), CFG)
    assert d.level == 2 and d.needs_human and any("above historical" in r for r in d.reasons)


def test_accepted_anomaly_does_not_retrigger():
    assert decide(facts(price_delta_pct=18.0, anomaly_accepted=True), report(), CFG).level == 1


def test_level2_for_amount_over_auto_limit_and_manager_role():
    d = decide(facts(amount=91_000, budget=100_000), report("manager"), CFG)
    assert d.level == 2 and d.required_role == "manager"


def test_level3_human_decision_for_high_value_or_unapproved_vendor():
    assert decide(facts(amount=300_000, budget=350_000), report("admin"), CFG).level == 3
    d = decide(facts(vendor_approved=False), report(), CFG)
    assert d.level == 3 and d.outcome == "human_decision" and d.required_role == "manager"
    assert decide(facts(amount=60_000, budget=50_000), report(), CFG).level == 3  # over budget


def test_existing_grant_covers_substitution():
    grant = {"role": "manager", "by": "Meera", "max_amount": 95_000}
    d = decide(facts(amount=91_000, budget=100_000, grant=grant), report("manager"), CFG)
    assert d.level == 2 and d.approval_covered and not d.needs_human
    d2 = decide(facts(amount=99_000, budget=100_000, grant=grant), report("manager"), CFG)
    assert d2.needs_human


def test_rules_are_configurable():
    policies = [NS(enabled=True, rule_type="auto_execute_limit", params={"max_amount": 150_000}),
                NS(enabled=True, rule_type="price_anomaly", params={"threshold_pct": 25})]
    cfg = DecisionConfig.from_policies(policies)
    assert decide(facts(amount=91_000, budget=100_000, price_delta_pct=18), report(), cfg).level == 1
