"""Policy engine. Rules are *data* (rows in the policies table); this module only knows how to
interpret a rule_type. Pure functions: no database or network access, fully unit-testable."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from app.core.security import ROLE_RANK


class PolicyLike(Protocol):
    key: str
    name: str
    category: str
    rule_type: str
    params: dict
    severity: str
    enabled: bool


@dataclass
class PolicyResult:
    key: str
    name: str
    category: str
    status: str  # pass | warn | fail
    message: str
    severity: str = "block"
    approval_role: str | None = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PolicyReport:
    results: list[PolicyResult] = field(default_factory=list)

    @property
    def blocking(self) -> list[PolicyResult]:
        return [r for r in self.results if r.status == "fail" and r.severity == "block"]

    @property
    def warnings(self) -> list[PolicyResult]:
        return [r for r in self.results if r.status == "warn" or (r.status == "fail" and r.severity != "block")]

    @property
    def approvals_required(self) -> list[PolicyResult]:
        return [r for r in self.results if r.approval_role]

    @property
    def required_role(self) -> str | None:
        roles = [r.approval_role for r in self.approvals_required if r.approval_role]
        return max(roles, key=lambda role: ROLE_RANK.get(role, 0)) if roles else None

    @property
    def passed(self) -> bool:
        return not self.blocking

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "required_role": self.required_role,
            "results": [r.to_dict() for r in self.results],
        }


Handler = Callable[[PolicyLike, dict[str, Any]], "PolicyResult | None"]
RULE_HANDLERS: dict[str, Handler] = {}


def rule(rule_type: str):
    def deco(fn: Handler) -> Handler:
        RULE_HANDLERS[rule_type] = fn
        return fn

    return deco


def _res(policy: PolicyLike, status: str, message: str, approval_role: str | None = None) -> PolicyResult:
    return PolicyResult(policy.key, policy.name, policy.category, status, message, policy.severity, approval_role)


def inr(amount: float | int | None) -> str:
    """Indian digit grouping: 100000 -> ₹1,00,000."""
    if amount is None:
        return "—"
    s = str(int(round(amount)))
    if len(s) <= 3:
        return "₹" + s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join(groups + [tail])


@rule("allowed_categories")
def _allowed_categories(p, facts):
    category = facts.get("category")
    allowed = p.params.get("categories", [])
    if category in allowed:
        return _res(p, "pass", f"Category '{category}' is an approved procurement category")
    return _res(p, "fail", f"Category '{category}' is not an approved procurement category (allowed: {', '.join(allowed)})")


@rule("budget_limit")
def _budget_limit(p, facts):
    amount = facts.get("total") or facts.get("budget")
    limit = p.params.get("max_amount", 0)
    if amount is None:
        return _res(p, "fail", "No budget supplied; a budget is required for every request")
    if amount <= limit:
        return _res(p, "pass", f"{inr(amount)} is within the per-request limit of {inr(limit)}")
    return _res(p, "fail", f"{inr(amount)} exceeds the per-request limit of {inr(limit)}")


@rule("quantity_limit")
def _quantity_limit(p, facts):
    qty = facts.get("quantity") or 0
    limit = p.params.get("max_quantity", 0)
    if qty <= limit:
        return _res(p, "pass", f"Quantity {qty} is within the limit of {limit} units")
    return _res(p, "fail", f"Quantity {qty} exceeds the limit of {limit} units per request")


@rule("approval_threshold")
def _approval_threshold(p, facts):
    amount = facts.get("total") or facts.get("budget") or 0
    threshold = p.params.get("amount", 0)
    role = p.params.get("role", "manager")
    if amount >= threshold:
        return _res(p, "warn", f"{inr(amount)} is at or above {inr(threshold)}: {role} approval required", approval_role=role)
    return _res(p, "pass", f"{inr(amount)} is below {inr(threshold)}: no {role} approval needed")


@rule("required_fields")
def _required_fields(p, facts):
    missing = [f for f in p.params.get("fields", []) if not facts.get(f)]
    if missing:
        return _res(p, "fail", "Missing required documentation: " + ", ".join(missing))
    return _res(p, "pass", "All required request fields are documented")


@rule("hr_verification")
def _hr_verification(p, facts):
    purpose = (facts.get("purpose") or "").lower()
    keywords = p.params.get("purpose_keywords", [])
    applies = facts.get("category") in p.params.get("categories", []) and any(k in purpose for k in keywords)
    if not applies:
        return _res(p, "pass", "HR verification not applicable to this request")
    verified = facts.get("hr_verified")
    if verified is True:
        return _res(p, "pass", "Employee requirement verified against the HR system")
    if verified is None:
        return _res(p, "warn", "Employee requirement could not be checked (HR system unavailable)")
    return _res(p, "fail", "No matching new-hire record found in the HR system")


@rule("vendor_approved_required")
def _vendor_approved(p, facts):
    vendor = facts.get("vendor")
    if vendor is None:
        return None  # evaluated once a vendor is selected
    if vendor.get("approved"):
        return _res(p, "pass", f"{vendor['name']} is on the approved vendor list")
    return _res(p, "fail", f"{vendor['name']} is not an approved vendor")


@rule("min_vendor_quotes")
def _min_quotes(p, facts):
    compared = facts.get("vendors_compared")
    if compared is None:
        return None
    needed = p.params.get("min", 2)
    if compared >= needed:
        return _res(p, "pass", f"{compared} vendors compared (minimum {needed})")
    return _res(p, "warn", f"Only {compared} vendor(s) compared; policy asks for {needed}")


def evaluate(facts: dict[str, Any], policies: list[PolicyLike], categories: set[str] | None = None) -> PolicyReport:
    report = PolicyReport()
    for policy in policies:
        if not policy.enabled:
            continue
        if categories and policy.category not in categories:
            continue
        handler = RULE_HANDLERS.get(policy.rule_type)
        if not handler:
            continue
        result = handler(policy, facts)
        if result is not None:
            report.results.append(result)
    return report


def validate_params(rule_type: str, params: dict) -> str | None:
    """Server-side validation of administrator edits. Returns an error message or None."""
    num = (int, float)
    schemas = {
        "allowed_categories": {"categories": list},
        "budget_limit": {"max_amount": num},
        "quantity_limit": {"max_quantity": num},
        "approval_threshold": {"amount": num, "role": str},
        "required_fields": {"fields": list},
        "min_vendor_quotes": {"min": num},
        "auto_execute_limit": {"max_amount": num},
        "human_decision_limit": {"min_amount": num},
        "price_anomaly": {"threshold_pct": num},
        "min_alt_reliability": {"min": num},
        "vendor_scoring": {"weights": dict},
    }
    expected = schemas.get(rule_type)
    if expected is None:
        return None
    for key, typ in expected.items():
        if key not in params:
            return f"Missing parameter '{key}'"
        if not isinstance(params[key], typ) or isinstance(params[key], bool):
            return f"Parameter '{key}' has the wrong type"
        if typ is num and params[key] < 0:
            return f"Parameter '{key}' must not be negative"
    if rule_type == "approval_threshold" and params["role"] not in ROLE_RANK:
        return "Unknown approval role"
    return None
