"""Relational data model. Every domain concept has its own table; JSON is only used for
genuinely schemaless payloads (step I/O, supporting data, rule parameters)."""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import SCHEMA, Base, utcnow


def _fk(target: str, **kw):
    return ForeignKey(f"{SCHEMA}.{target}", **kw)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(_fk("organizations.id"))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(30))  # requester|auditor|approver|manager|admin
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BusinessFunction(Base):
    __tablename__ = "business_functions"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(_fk("organizations.id"))
    key: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="coming_soon")  # active|coming_soon
    outcome: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_policies_org_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(_fk("organizations.id"))
    function_key: Mapped[str] = mapped_column(String(50), default="procurement")
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30))  # budget|category|approval|vendor|documentation|organization|decision|exception
    rule_type: Mapped[str] = mapped_column(String(60))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(10), default="block")  # block|warn
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(_fk("organizations.id"))
    name: Mapped[str] = mapped_column(String(200))
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    catalog: Mapped[dict] = mapped_column(JSON, default=dict)  # category -> unit price (INR)
    historical_avg: Mapped[dict] = mapped_column(JSON, default=dict)  # category -> avg unit price (INR)
    rating: Mapped[float] = mapped_column(Float, default=4.0)
    warranty_years: Mapped[int] = mapped_column(Integer, default=1)
    delivery_days: Mapped[int] = mapped_column(Integer, default=5)
    reliability_score: Mapped[float] = mapped_column(Float, default=90.0)  # historical on-time/in-spec %
    compliance_score: Mapped[float] = mapped_column(Float, default=90.0)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Request(Base):
    __tablename__ = "requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(_fk("organizations.id"))
    requester_id: Mapped[int] = mapped_column(_fk("users.id"))
    function_key: Mapped[str] = mapped_column(String(50), default="procurement")
    source: Mapped[str] = mapped_column(String(20), default="text")  # web_form|text|email|api
    raw_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="extracted")  # extracted|executing|closed
    item: Mapped[str | None] = mapped_column(String(300), nullable=True)
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(300), nullable=True)
    required_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    required_date_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    requester_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extraction_engine: Mapped[str] = mapped_column(String(80), default="heuristic")
    extraction_notes: Mapped[list] = mapped_column(JSON, default=list)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_faults: Mapped[list] = mapped_column(JSON, default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    requester = relationship("User", lazy="joined")


class Workflow(Base):
    __tablename__ = "workflows"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(_fk("organizations.id"))
    function_key: Mapped[str] = mapped_column(String(50), index=True)
    definition_key: Mapped[str] = mapped_column(String(80))
    request_id: Mapped[int | None] = mapped_column(_fk("requests.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(_fk("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending|running|waiting_human|completed|failed|cancelled
    current_step_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict)  # persisted working state (resumable)
    plan: Mapped[list] = mapped_column(JSON, default=list)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_data: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    step_delay: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    runner_owner: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    runner_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    request = relationship("Request", lazy="joined")
    steps = relationship("WorkflowStep", order_by="WorkflowStep.position", lazy="select", cascade="all, delete-orphan")


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(_fk("workflows.id"), index=True)
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30), default="automated")  # automated|decision|approval
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending|running|completed|failed|waiting_human|resolved|skipped
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(_fk("workflows.id"), index=True)
    step_id: Mapped[int | None] = mapped_column(_fk("workflow_steps.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))  # autonomy|vendor_selection|human_approval|exception_resolution
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 auto, 2 review, 3 human decision
    outcome: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)
    rule_trace: Mapped[list] = mapped_column(JSON, default=list)
    actor: Mapped[str] = mapped_column(String(200), default="FlowForge Decision Engine")
    actor_type: Mapped[str] = mapped_column(String(10), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowException(Base):
    __tablename__ = "exceptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(_fk("workflows.id"), index=True)
    step_id: Mapped[int | None] = mapped_column(_fk("workflow_steps.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(60))
    category: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    recoverable: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    # retrying|resolving|auto_resolved|awaiting_review|escalated|resolved_by_human|rejected|failed
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_trace: Mapped[list] = mapped_column(JSON, default=list)
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(_fk("workflows.id"), index=True)
    step_id: Mapped[int | None] = mapped_column(_fk("workflow_steps.id"), nullable=True)
    exception_id: Mapped[int | None] = mapped_column(_fk("exceptions.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="approval")  # approval|exception_review
    level: Mapped[int] = mapped_column(Integer, default=2)  # 2 review, 3 human decision
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)  # what happened
    reason: Mapped[str] = mapped_column(Text)  # why it happened / why a human is needed
    recommendation: Mapped[str] = mapped_column(Text)
    risk: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(10), default="medium")
    supporting_data: Mapped[dict] = mapped_column(JSON, default=dict)
    options: Mapped[list] = mapped_column(JSON, default=list)
    assigned_role: Mapped[str] = mapped_column(String(30), default="approver")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending|approved|rejected|modified
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decided_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    modification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_integrations_org_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(_fk("organizations.id"))
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(100), default="Simulated")
    mode: Mapped[str] = mapped_column(String(10), default="mock")  # mock|live
    status: Mapped[str] = mapped_column(String(20), default="connected")  # connected|degraded|disconnected
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    calls_total: Mapped[int] = mapped_column(Integer, default=0)
    failures_total: Mapped[int] = mapped_column(Integer, default=0)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(_fk("organizations.id"))
    workflow_id: Mapped[int | None] = mapped_column(_fk("workflows.id"), nullable=True, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_type: Mapped[str] = mapped_column(String(10))  # system|ai|user|tool
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100), index=True)
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[str] = mapped_column(String(30), default="ok")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="recorded")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiMetric(Base):
    __tablename__ = "api_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    path: Mapped[str] = mapped_column(String(300))
    status_code: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    org_id: Mapped[int | None] = mapped_column(_fk("organizations.id"), nullable=True, index=True)


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(_fk("workflows.id"), index=True)
    step_id: Mapped[int] = mapped_column(_fk("workflow_steps.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="started")  # started|completed|failed
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(_fk("workflows.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(_fk("vendors.id"))
    po_number: Mapped[str] = mapped_column(String(40), unique=True)
    item: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|issued|confirmed|fulfilled
    erp_ref: Mapped[str | None] = mapped_column(String(60), nullable=True)
    accounting_ref: Mapped[str | None] = mapped_column(String(60), nullable=True)
    document_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expected_delivery: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vendor = relationship("Vendor", lazy="joined")


class WorkflowDefinitionRecord(Base):
    """A user-built workflow. Each version is its own immutable-once-published row, and every execution is pinned to
    the exact row it started on (definition_key = "custom:<id>"), so later edits never change running work."""
    __tablename__ = "workflow_definitions"
    __table_args__ = (UniqueConstraint("org_id", "key", "version", name="uq_workflow_definitions_org_key_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(_fk("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(60))
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published | archived
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    tests: Mapped[list] = mapped_column(JSON, default=list)
    template_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_by: Mapped[int | None] = mapped_column(_fk("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
