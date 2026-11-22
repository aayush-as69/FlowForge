"""Decision engine: decides whether FlowForge may proceed autonomously.

Levels
  1  AUTO-EXECUTE     routine, low risk
  2  REVIEW           ambiguous/unusual: pause for a reviewer
  3  HUMAN DECISION   high impact: a accountable human makes the final call

Thresholds are configuration (policy rows), never constants buried in UI or step code."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.security import ROLE_RANK
from app.services.policy_engine import PolicyReport, inr

LEVEL_NAMES = {1: "auto_execute", 2: "review", 3: "human_decision"}


@dataclass
class DecisionConfig:
    auto_limit: int = 50_000
    human_limit: int = 250_000
    anomaly_pct: float = 15.0
    min_alt_reliability: float = 95.0

    @classmethod
    def from_policies(cls, policies) -> "DecisionConfig":
        cfg = cls()
        for p in policies:
            if not p.enabled:
                continue
            if p.rule_type == "auto_execute_limit":
                cfg.auto_limit = int(p.params.get("max_amount", cfg.auto_limit))
            elif p.rule_type == "human_decision_limit":
                cfg.human_limit = int(p.params.get("min_amount", cfg.human_limit))
            elif p.rule_type == "price_anomaly":
                cfg.anomaly_pct = float(p.params.get("threshold_pct", cfg.anomaly_pct))
            elif p.rule_type == "min_alt_reliability":
                cfg.min_alt_reliability = float(p.params.get("min", cfg.min_alt_reliability))
        return cfg


@dataclass
class DecisionResult:
    level: int
    reasons: list[str]
    trace: list[dict[str, Any]]
    required_role: str | None = None
    approval_covered: bool = False

    @property
    def outcome(self) -> str:
        return LEVEL_NAMES[self.level]

    @property
    def needs_human(self) -> bool:
        return self.level > 1 and not self.approval_covered

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "outcome": self.outcome,
            "reasons": self.reasons,
            "trace": self.trace,
            "required_role": self.required_role,
            "approval_covered": self.approval_covered,
        }


def decide(facts: dict[str, Any], report: PolicyReport, cfg: DecisionConfig) -> DecisionResult:
    """facts: amount, budget, vendor_approved, price_delta_pct, anomaly_accepted, grant{role,max_amount,vendor_id,by}, vendor_id"""
    trace: list[dict[str, Any]] = []
    reasons: list[str] = []
    amount = facts.get("amount") or 0
    level = 1

    def check(rule: str, matched: bool, detail: str, raises_to: int = 1):
        nonlocal level
        trace.append({"rule": rule, "matched": matched, "detail": detail, "level": raises_to if matched else 1})
        if matched:
            level = max(level, raises_to)
            reasons.append(detail)

    # --- Level 3: high-impact / accountability ---------------------------------------------
    check("human_decision_limit", amount >= cfg.human_limit,
          f"Order value {inr(amount)} ≥ {inr(cfg.human_limit)} high-impact threshold" if amount >= cfg.human_limit
          else f"Order value {inr(amount)} below high-impact threshold {inr(cfg.human_limit)}", 3)
    check("vendor_approved", facts.get("vendor_approved") is False,
          "Selected vendor is not on the approved list" if facts.get("vendor_approved") is False
          else "Selected vendor is approved", 3)
    budget = facts.get("budget")
    over_budget = budget is not None and amount > budget
    check("within_budget", over_budget,
          f"Order value {inr(amount)} exceeds approved budget {inr(budget)}" if over_budget
          else f"Order value {inr(amount)} within approved budget {inr(budget)}", 3)
    check("policy_blocking", bool(report.blocking),
          "Blocking policy failures: " + "; ".join(r.message for r in report.blocking) if report.blocking
          else "No blocking policy failures", 3)

    # --- Level 2: ambiguous / unusual ------------------------------------------------------
    check("auto_execute_limit", amount > cfg.auto_limit,
          f"Order value {inr(amount)} exceeds the autonomous limit of {inr(cfg.auto_limit)}" if amount > cfg.auto_limit
          else f"Order value {inr(amount)} within the autonomous limit of {inr(cfg.auto_limit)}", 2)
    delta = facts.get("price_delta_pct")
    anomaly = delta is not None and delta > cfg.anomaly_pct and not facts.get("anomaly_accepted")
    check("price_anomaly", anomaly,
          f"Unit price is {delta}% above historical average (threshold {cfg.anomaly_pct:g}%)" if anomaly
          else "No unaccepted price anomaly", 2)
    approvals = report.approvals_required
    check("policy_approval_required", bool(approvals),
          "Policy requires approval: " + "; ".join(f"{r.approval_role} ({r.name})" for r in approvals) if approvals
          else "No policy-mandated approvals", 2)
    check("policy_warnings", bool([w for w in report.warnings if not w.approval_role]),
          "Policy warnings: " + "; ".join(w.message for w in report.warnings if not w.approval_role)
          if [w for w in report.warnings if not w.approval_role] else "No policy warnings", 2)

    required = report.required_role
    if level == 2 and not required:
        required = "approver"
    if level == 3:
        required = "admin" if amount >= cfg.human_limit * 2 or required == "admin" else "manager"
        if required == "manager" and report.required_role == "admin":
            required = "admin"

    # --- Prior approval grant (modify / vendor substitution) --------------------------------
    covered = False
    grant = facts.get("grant")
    if level >= 2 and grant:
        within = amount <= grant.get("max_amount", 0)
        role_ok = ROLE_RANK.get(grant.get("role", ""), -1) >= ROLE_RANK.get(required or "approver", 0)
        enough = level == 2 or ROLE_RANK.get(grant.get("role", ""), -1) >= ROLE_RANK.get(required or "", 0)
        covered = within and role_ok and enough and not over_budget and not report.blocking
        trace.append({
            "rule": "existing_approval_grant", "matched": covered,
            "detail": (f"Existing approval by {grant.get('by')} ({grant.get('role')}) covers up to {inr(grant.get('max_amount'))}"
                       if covered else "Existing approval does not cover the current terms"),
            "level": 1,
        })
        if covered:
            reasons.append(f"Approval already granted by {grant.get('by')} covers this order")
    if level == 1:
        reasons = ["All rules satisfied: within limits, approved vendor, policies satisfied — executing autonomously"]
        required = None
    return DecisionResult(level=level, reasons=reasons, trace=trace, required_role=required, approval_covered=covered)
