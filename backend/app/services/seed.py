"""Demo data. Base seed = organisation, users, functions, policies, vendors, integrations.
History seed = realistic past workflows produced by running the REAL engine (then back-dated)."""
from __future__ import annotations

import logging
import random
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.security import hash_password
from app.models import (Approval, AuditEvent, BusinessFunction, Decision, Integration, Organization, Policy, PurchaseOrder,
                        Request, User, Vendor, Workflow, WorkflowException, WorkflowStep)
from app.services import approvals as approval_service
from app.services import requests as request_service
from app.workflows import engine as wf_engine

log = logging.getLogger("flowforge.seed")

USERS = [
    ("admin@flowforge.demo", "Aarav Kapoor", "admin", "Operations"),
    ("manager@flowforge.demo", "Meera Iyer", "manager", "Engineering"),
    ("approver@flowforge.demo", "Priya Nair", "approver", "Procurement"),
    ("requester@flowforge.demo", "Ananya Rao", "requester", "Engineering"),
    ("auditor@flowforge.demo", "Vikram Shah", "auditor", "Compliance"),
    ("karthik@flowforge.demo", "Karthik Menon", "requester", "IT Operations"),
    ("sneha@flowforge.demo", "Sneha Joshi", "requester", "Finance"),
]

FUNCTIONS = [
    ("procurement", "Procurement", "From purchase request to purchase order, ERP posting and verified fulfilment.", "active",
     "Request → vendor selection → PO → ERP → verified delivery"),
    ("finance_ops", "Finance Operations", "Invoice matching, payment runs and month-end reconciliation.", "coming_soon",
     "Invoice → match → approve → pay → reconcile"),
    ("employee_onboarding", "Employee Onboarding", "Accounts, equipment, access and orientation for every new joiner.", "coming_soon",
     "Offer accepted → provisioned → day-one ready"),
    ("collections", "Collections", "Dunning, payment follow-up and dispute resolution.", "coming_soon",
     "Overdue → contact → resolve → cash received"),
    ("compliance", "Compliance", "Continuous control testing, evidence collection and reporting.", "coming_soon",
     "Control → evidence → test → remediate"),
]

CATEGORIES = ["laptop", "monitor", "peripherals", "furniture", "software", "networking"]

POLICIES = [
    ("allowed_categories", "Approved procurement categories", "category", "allowed_categories", {"categories": CATEGORIES}, "block",
     "Only these categories may be procured through FlowForge. Anything else is blocked for administrator review."),
    ("budget_limit", "Per-request budget ceiling", "budget", "budget_limit", {"max_amount": 1_000_000}, "block",
     "Requests above this value must go through formal tendering."),
    ("quantity_limit", "Maximum quantity per request", "budget", "quantity_limit", {"max_quantity": 50}, "block",
     "Guards against fat-finger and bulk-buy errors."),
    ("approval_manager", "Manager approval threshold", "approval", "approval_threshold", {"amount": 50_000, "role": "manager"}, "warn",
     "Spend at or above this amount needs manager approval."),
    ("approval_admin", "Executive approval threshold", "approval", "approval_threshold", {"amount": 250_000, "role": "admin"}, "warn",
     "High-value spend needs an accountable executive decision."),
    ("required_fields", "Request documentation", "documentation", "required_fields", {"fields": ["purpose", "required_date"]}, "warn",
     "Purpose and required date must be documented for audit."),
    ("hr_new_hire", "New-hire equipment verified in HR", "organization", "hr_verification",
     {"categories": ["laptop", "monitor", "peripherals"],
      "purpose_keywords": ["new employee", "new hire", "joining", "onboard", "joiner"]}, "warn",
     "If equipment is requested for a new joiner, the HR system must confirm the hire."),
    ("vendor_approved", "Approved vendors only", "vendor", "vendor_approved_required", {}, "block",
     "Purchase orders may only be placed with vendors on the approved list."),
    ("min_quotes", "Minimum vendor comparison", "vendor", "min_vendor_quotes", {"min": 2}, "warn",
     "At least two eligible vendors should be compared."),
    ("vendor_scoring", "Vendor scoring weights", "vendor", "vendor_scoring",
     {"weights": {"price": 0.25, "delivery": 0.20, "rating": 0.20, "warranty": 0.10, "reliability": 0.20, "compliance": 0.05}}, "warn",
     "Relative importance of each factor when ranking vendors (should sum to 1)."),
    ("auto_limit", "Autonomous execution limit (Level 1)", "decision", "auto_execute_limit", {"max_amount": 50_000}, "warn",
     "At or below this value, with an approved vendor and clean policies, FlowForge executes without a human."),
    ("human_limit", "Human decision threshold (Level 3)", "decision", "human_decision_limit", {"min_amount": 250_000}, "warn",
     "At or above this value a human must make the final, accountable decision."),
    ("price_anomaly", "Price anomaly threshold", "decision", "price_anomaly", {"threshold_pct": 15}, "warn",
     "A quote this far above the vendor's historical average triggers an exception and review."),
    ("min_alt_reliability", "Minimum reliability for auto-substitution", "exception", "min_alt_reliability", {"min": 95}, "warn",
     "FlowForge will only substitute an alternative vendor automatically if its reliability meets this score."),
]

BASE = {"laptop": 80_000, "monitor": 28_000, "peripherals": 3_200, "furniture": 14_000, "software": 9_000, "networking": 85_000}
# name, approved, available, price mult, hist mult, delivery, rating, warranty, reliability, compliance, categories, email
VENDORS = [
    ("Apex Technologies", True, True, 1.00, 0.98, 3, 4.7, 3, 94, 96, CATEGORIES, "sales@apex-tech.example"),
    ("Bluepeak Systems", True, True, 1.06, 0.95, 2, 4.9, 3, 98, 100, CATEGORIES, "orders@bluepeak.example"),
    ("Corvus IT Supplies", True, True, 0.93, 0.94, 7, 4.2, 1, 88, 92, CATEGORIES[:-1], "supply@corvus-it.example"),
    ("Dealzone Traders", False, True, 0.85, 0.87, 2, 4.0, 1, 71, 60, ["laptop", "monitor", "peripherals"], "hello@dealzone.example"),
    ("Everline Computers", True, False, 1.03, 1.00, 4, 4.5, 2, 90, 94, ["laptop", "furniture"], "b2b@everline.example"),
]
LAPTOP = {"Apex Technologies": (82_000, 80_000), "Bluepeak Systems": (91_000, 77_100), "Corvus IT Supplies": (76_000, 75_200),
          "Dealzone Traders": (69_000, 70_000), "Everline Computers": (88_000, 86_500)}

INTEGRATIONS = [
    ("erp", "ERP", "Purchase orders, GL postings and commitments", "SAP S/4HANA (simulated)",
     ["Create purchase order", "Post GL commitment", "Read cost centres"]),
    ("vendor_db", "Vendor Database", "Vendor master data, catalogs, availability and order confirmation", "Vendor Master (simulated)",
     ["Search vendors", "Confirm availability", "Confirm order"]),
    ("hr", "HR System", "Employee records, joiners and equipment entitlement", "Workday (simulated)", ["Verify new hire"]),
    ("crm", "CRM", "Stakeholder, department and cost-centre context", "Salesforce (simulated)", ["Look up stakeholder"]),
    ("email", "Email", "Notifications to vendors and requesters", "Microsoft 365 Mail (simulated)", ["Send email"]),
    ("accounting", "Accounting", "Budget checks, commitments and invoice matching", "NetSuite (simulated)",
     ["Check budget", "Reserve commitment", "Three-way match"]),
    ("documents", "Document Storage", "Request archives and purchase order documents", "SharePoint (simulated)", ["Store document"]),
]


def seed_base(db: Session) -> Organization:
    org = db.query(Organization).first()
    if org:
        return org
    org = Organization(name="Meridian Industries")
    db.add(org)
    db.flush()
    pw = hash_password(settings.demo_password)
    for email, name, role, dept in USERS:
        db.add(User(org_id=org.id, email=email, name=name, role=role, department=dept, password_hash=pw))
    for i, (key, name, desc, status, outcome) in enumerate(FUNCTIONS):
        db.add(BusinessFunction(org_id=org.id, key=key, name=name, description=desc, status=status, outcome=outcome, sort_order=i))
    for key, name, cat, rule, params, sev, desc in POLICIES:
        db.add(Policy(org_id=org.id, key=key, name=name, category=cat, rule_type=rule, params=params, severity=sev, description=desc))
    for name, approved, avail, pm, hm, days, rating, warranty, rel, comp, cats, email in VENDORS:
        catalog = {c: round(BASE[c] * pm / 100) * 100 for c in cats}
        hist = {c: round(BASE[c] * hm / 100) * 100 for c in cats}
        if "laptop" in cats:
            catalog["laptop"], hist["laptop"] = LAPTOP[name]
        db.add(Vendor(org_id=org.id, name=name, approved=approved, available=avail, categories=cats, catalog=catalog,
                      historical_avg=hist, rating=rating, warranty_years=warranty, delivery_days=days, reliability_score=rel,
                      compliance_score=comp, contact_email=email,
                      notes=None if approved else "Not onboarded: failed compliance review"))
    for key, name, desc, provider, caps in INTEGRATIONS:
        db.add(Integration(org_id=org.id, key=key, name=name, description=desc, provider=provider, mode="mock",
                           status="connected", latency_ms=60, last_checked_at=utcnow(), capabilities=caps))
    db.commit()
    return org


# ------------------------------------------------------------------------------------------ history
HISTORY_TEMPLATES = [
    ("Need {n} wireless keyboard and mouse sets for the support team. Budget ₹{b}. Needed by next Friday.", "peripherals", (3, 8), (24_000, 40_000), []),
    ("Please buy {n} docking stations for the design team, budget ₹{b}, required in 5 days.", "peripherals", (2, 6), (22_000, 38_000), []),
    ("Requesting {n} ergonomic chairs for the new floor. Budget ₹{b}. Required by next Monday. Purpose: team expansion", "furniture", (2, 3), (42_000, 48_000), []),
    ("Need {n} 27-inch monitors for the developer team. Budget ₹{b}. Required by next Thursday.", "monitor", (4, 5), (130_000, 160_000), []),
    ("{n} software licences for the analytics team, budget ₹{b}, needed by next Wednesday. Purpose: team expansion", "software", (6, 12), (95_000, 130_000), []),
    ("I need a laptop for a new employee joining next Monday. Budget is ₹1,00,000.", "laptop", (1, 1), (100_000, 100_000), ["erp_timeout"]),
    ("Need {n} monitors for the finance team. Budget ₹{b}. Needed by next Friday.", "monitor", (4, 4), (125_000, 150_000), ["vendor_unavailable"]),
    ("Replacement keyboard and mouse for {n} employees, budget ₹{b}, needed by tomorrow.", "peripherals", (1, 4), (12_000, 22_000), ["erp_timeout"]),
    ("Purchase {n} network switches for the branch office. Budget ₹{b}. Required by next Friday. Purpose: team expansion", "networking", (3, 4), (280_000, 380_000), []),
]
WEIGHTS = [9, 8, 5, 2, 1, 2, 1, 7, 1]


def _decide_all(db: Session, wf: Workflow, users: dict[str, User], rng: random.Random) -> None:
    for _ in range(6):
        db.refresh(wf)
        if wf.status != "waiting_human":
            return
        approval = db.query(Approval).filter(Approval.workflow_id == wf.id, Approval.status == "pending").first()
        user = users["admin"] if approval.assigned_role == "admin" else users["manager"] if approval.assigned_role == "manager" else users["approver"]
        approval_service.decide(db, approval, user, "approve", "Approved after review of vendor comparison and policy results", None)
        wf_engine.run(db, wf.id)


def _shift(db: Session, wf: Workflow, delta: timedelta) -> None:
    def move(obj, *cols):
        for c in cols:
            v = getattr(obj, c)
            if v is not None:
                setattr(obj, c, v - delta)

    move(wf, "created_at", "started_at", "completed_at", "updated_at")
    if wf.request:
        move(wf.request, "created_at", "updated_at")
    for s in db.query(WorkflowStep).filter(WorkflowStep.workflow_id == wf.id):
        move(s, "started_at", "completed_at", "updated_at")
    for model, cols in ((Decision, ("created_at",)), (WorkflowException, ("detected_at", "resolved_at")),
                        (Approval, ("created_at", "decided_at")), (AuditEvent, ("ts",)), (PurchaseOrder, ("created_at",))):
        for row in db.query(model).filter(model.workflow_id == wf.id):
            move(row, *cols)
    db.flush()


def seed_history(db: Session, count: int = 34) -> None:
    if db.query(Workflow).count():
        return
    rng = random.Random(11)
    users = {u.email.split("@")[0]: u for u in db.query(User).all()}
    requesters = [users["requester"], users["karthik"], users["sneha"]]
    saved_delay = settings.retry_backoff
    settings.retry_backoff = 0
    try:
        for i in range(count):
            tpl, cat, qty_rng, budget_rng, faults = rng.choices(HISTORY_TEMPLATES, weights=WEIGHTS)[0]
            n = rng.randint(*qty_rng)
            b = rng.randrange(budget_rng[0], budget_rng[1] + 1, 1000)
            text = tpl.format(n=n, b=format(b, ","))
            requester = rng.choice(requesters)
            req = request_service.create_request(db, requester, text=text, fields=None, source=rng.choice(["web_form", "text", "email", "api"]),
                                                 demo_faults=faults)
            if request_service.missing_fields(req):
                continue
            wf = request_service.start_workflow(db, req, requester, step_delay=0)
            wf_engine.run(db, wf.id)
            _decide_all(db, wf, users, rng)
            hours_ago = rng.uniform(0.3, 9) if i < 10 else rng.uniform(9, 24 * 13)
            _shift(db, wf, timedelta(hours=hours_ago))
            db.commit()
        _seed_inflight(db, users)
    finally:
        settings.retry_backoff = saved_delay


def _seed_inflight(db: Session, users: dict[str, User]) -> None:
    def launch(requester: str, text: str, faults: list[str] | None = None):
        req = request_service.create_request(db, users[requester], text=text, fields=None, source="text", demo_faults=faults or [])
        wf = request_service.start_workflow(db, req, users[requester], step_delay=0)
        wf_engine.run(db, wf.id)
        return wf

    launch("karthik", "Need 4 27-inch monitors for the platform team. Budget ₹1,40,000. Required by next Thursday.")
    launch("sneha", "Purchase 4 network switches for the Pune office. Budget ₹3,80,000. Required by next Friday. Purpose: team expansion")
    wf = launch("requester", "Laptop for a new hire joining next Monday. Budget ₹1,00,000. Needs 32GB RAM.")
    # a second laptop request whose review is escalated by the first-line approver
    wf2 = launch("sneha", "I need a laptop for a new employee joining next Monday. Budget is ₹1,00,000.")
    approval = db.query(Approval).filter(Approval.workflow_id == wf2.id, Approval.status == "pending").first()
    if approval:
        approval_service.decide(db, approval, users["approver"], "escalate",
                                "Premium is material and I would like a manager to own this call", None)
    failed = launch("karthik", "Need 6 docking stations for the design team. Budget ₹30,000. Required by next Friday.", ["invoice_mismatch"])
    db.refresh(failed)
    for w, mins in ((wf, 38), (wf2, 22), (failed, 55)):
        _shift(db, w, timedelta(minutes=mins))
    db.commit()
