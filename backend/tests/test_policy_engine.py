from types import SimpleNamespace as NS

from app.services import policy_engine as pe
from app.services.policy_engine import inr


def P(key, rule_type, params, category="budget", severity="block"):
    return NS(key=key, name=key, category=category, rule_type=rule_type, params=params, severity=severity, enabled=True)


POLICIES = [
    P("cats", "allowed_categories", {"categories": ["laptop", "monitor"]}, "category"),
    P("budget", "budget_limit", {"max_amount": 500_000}),
    P("mgr", "approval_threshold", {"amount": 50_000, "role": "manager"}, "approval", "warn"),
    P("exec", "approval_threshold", {"amount": 250_000, "role": "admin"}, "approval", "warn"),
]


def facts(**kw):
    return {"category": "laptop", "quantity": 1, "budget": 100_000, **kw}


def test_valid_request_passes_with_manager_approval_flag():
    report = pe.evaluate(facts(), POLICIES)
    assert report.passed and not report.blocking
    assert report.required_role == "manager"
    assert any("Manager" in r.message or "manager" in r.message for r in report.approvals_required)


def test_budget_exceeded_blocks():
    report = pe.evaluate(facts(budget=900_000), POLICIES)
    assert not report.passed
    assert [r.key for r in report.blocking] == ["budget"]


def test_invalid_category_blocks():
    report = pe.evaluate(facts(category="server"), POLICIES)
    assert not report.passed
    assert "not an approved" in report.blocking[0].message


def test_small_order_requires_no_approval():
    report = pe.evaluate(facts(budget=20_000), POLICIES)
    assert report.passed and report.required_role is None


def test_highest_approval_role_wins_and_disabled_policies_ignored():
    assert pe.evaluate(facts(budget=300_000), POLICIES).required_role == "admin"
    disabled = [NS(**{**p.__dict__, "enabled": False}) if p.key == "exec" else p for p in POLICIES]
    assert pe.evaluate(facts(budget=300_000), disabled).required_role == "manager"


def test_vendor_rules_wait_for_vendor_and_hr_rule():
    rules = [P("v", "vendor_approved_required", {}, "vendor"),
             P("hr", "hr_verification", {"categories": ["laptop"], "purpose_keywords": ["new employee"]}, "organization", "warn")]
    assert pe.evaluate(facts(), rules).results[0].key == "hr"  # vendor rule skipped until a vendor exists
    bad = pe.evaluate(facts(vendor={"name": "X", "approved": False}, purpose="New employee", hr_verified=False), rules)
    assert {r.key for r in bad.blocking} == {"v"} and any(r.key == "hr" and r.status == "fail" for r in bad.results)


def test_param_validation_and_inr_format():
    assert pe.validate_params("budget_limit", {"max_amount": -5})
    assert pe.validate_params("budget_limit", {"max_amount": 10}) is None
    assert pe.validate_params("approval_threshold", {"amount": 1, "role": "wizard"})
    assert inr(100000) == "₹1,00,000" and inr(1234567) == "₹12,34,567" and inr(950) == "₹950"
