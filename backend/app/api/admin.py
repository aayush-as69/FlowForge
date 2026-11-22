"""Policies, vendors, integrations, audit, dashboard and function catalogue."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.core.db import get_db, utcnow
from app.core.security import require
from app.integrations.adapters import check_health
from app.models import AuditEvent, BusinessFunction, Integration, Policy, Vendor, Workflow
from app.schemas.api import IntegrationUpdate, PolicyUpdate, VendorUpdate
from app.services import audit, dashboard, policy_engine

policies_router = APIRouter(prefix="/policies", tags=["policies"])
vendors_router = APIRouter(prefix="/vendors", tags=["vendors"])
integrations_router = APIRouter(prefix="/integrations", tags=["integrations"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])
functions_info_router = APIRouter(prefix="/functions", tags=["functions"])


def ser_policy(p: Policy) -> dict:
    return {"id": p.id, "key": p.key, "name": p.name, "category": p.category, "rule_type": p.rule_type, "params": p.params,
            "severity": p.severity, "enabled": p.enabled, "description": p.description, "version": p.version,
            "updated_by": p.updated_by, "updated_at": p.updated_at, "function_key": p.function_key}


@policies_router.get("")
def list_policies(db: Session = Depends(get_db), user=Depends(require("policies:read"))):
    return [ser_policy(p) for p in db.query(Policy).filter(Policy.org_id == user.org_id).order_by(Policy.id)]


@policies_router.patch("/{pid}")
def update_policy(pid: int, body: PolicyUpdate, db: Session = Depends(get_db), user=Depends(require("policies:write"))):
    p = db.get(Policy, pid)
    if p is None or p.org_id != user.org_id:
        raise HTTPException(404, "Policy not found.")
    before = ser_policy(p)
    if body.params is not None:
        err = policy_engine.validate_params(p.rule_type, body.params)
        if err:
            raise HTTPException(422, err)
        p.params = body.params
    if body.enabled is not None:
        p.enabled = body.enabled
    if body.severity is not None:
        p.severity = body.severity
    p.version += 1
    p.updated_by = user.name
    p.updated_at = utcnow()
    audit.record(db, org_id=user.org_id, workflow_id=None, actor_type="user", actor=user.name, action="policy.updated",
                 input={"policy": p.key, "before": {"params": before["params"], "enabled": before["enabled"], "severity": before["severity"]}},
                 output={"params": p.params, "enabled": p.enabled, "severity": p.severity, "version": p.version},
                 reason="Policy changed by administrator", status="applied")
    db.commit()
    return ser_policy(p)


def ser_vendor(v: Vendor) -> dict:
    return {"id": v.id, "name": v.name, "approved": v.approved, "available": v.available, "categories": v.categories,
            "catalog": v.catalog, "historical_avg": v.historical_avg, "rating": v.rating, "warranty_years": v.warranty_years,
            "delivery_days": v.delivery_days, "reliability_score": v.reliability_score, "compliance_score": v.compliance_score,
            "contact_email": v.contact_email, "notes": v.notes}


@vendors_router.get("")
def list_vendors(db: Session = Depends(get_db), user=Depends(require("vendors:read"))):
    return [ser_vendor(v) for v in db.query(Vendor).filter(Vendor.org_id == user.org_id).order_by(Vendor.id)]


@vendors_router.patch("/{vid}")
def update_vendor(vid: int, body: VendorUpdate, db: Session = Depends(get_db), user=Depends(require("vendors:write"))):
    v = db.get(Vendor, vid)
    if v is None or v.org_id != user.org_id:
        raise HTTPException(404, "Vendor not found.")
    changes = body.model_dump(exclude_unset=True)
    for k, val in changes.items():
        setattr(v, k, val)
    audit.record(db, org_id=user.org_id, workflow_id=None, actor_type="user", actor=user.name, action="vendor.updated",
                 input={"vendor": v.name}, output=changes, status="applied")
    db.commit()
    return ser_vendor(v)


def ser_integration(i: Integration) -> dict:
    return {"id": i.id, "key": i.key, "name": i.name, "description": i.description, "provider": i.provider, "mode": i.mode,
            "status": i.status, "latency_ms": i.latency_ms, "last_checked_at": i.last_checked_at, "capabilities": i.capabilities,
            "calls_total": i.calls_total, "failures_total": i.failures_total}


@integrations_router.get("")
def list_integrations(db: Session = Depends(get_db), user=Depends(require("integrations:read"))):
    return [ser_integration(i) for i in db.query(Integration).filter(Integration.org_id == user.org_id).order_by(Integration.id)]


def _own_integration(db: Session, user, key: str) -> Integration | None:
    return db.query(Integration).filter(Integration.key == key, Integration.org_id == user.org_id).first()


@integrations_router.post("/{key}/check")
def check(key: str, db: Session = Depends(get_db), user=Depends(require("integrations:manage"))):
    row = _own_integration(db, user, key)
    if row is None:
        raise HTTPException(404, "Integration not found.")
    check_health(db, row)
    db.commit()
    return ser_integration(row)


@integrations_router.patch("/{key}")
def update_integration(key: str, body: IntegrationUpdate, db: Session = Depends(get_db), user=Depends(require("integrations:manage"))):
    row = _own_integration(db, user, key)
    if row is None:
        raise HTTPException(404, "Integration not found.")
    row.status = body.status
    check_health(db, row)
    audit.record(db, org_id=user.org_id, workflow_id=None, actor_type="user", actor=user.name, action="integration.updated",
                 input={"integration": key}, output={"status": row.status}, status="applied")
    db.commit()
    return ser_integration(row)


@audit_router.get("")
def list_audit(workflow_id: int | None = None, actor_type: str | None = None, q: str | None = None, include_steps: bool = False,
               page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
               db: Session = Depends(get_db), user=Depends(require("audit:read"))):
    query = db.query(AuditEvent).filter(AuditEvent.org_id == user.org_id)
    if workflow_id:
        query = query.filter(AuditEvent.workflow_id == workflow_id)
    if actor_type:
        query = query.filter(AuditEvent.actor_type == actor_type)
    if not include_steps:
        query = query.filter(AuditEvent.action.notlike("step.%"))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(AuditEvent.action.ilike(like), AuditEvent.actor.ilike(like), AuditEvent.reason.ilike(like)))
    total = query.count()
    rows = query.order_by(AuditEvent.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ser.page([ser.ser_audit(e) for e in rows], total, page, page_size)


@dashboard_router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db), user=Depends(require("dashboard:read"))):
    return dashboard.summary(db, user.org_id)


@dashboard_router.get("/observability")
def observability(db: Session = Depends(get_db), user=Depends(require("dashboard:read"))):
    return dashboard.observability(db, user.org_id, dashboard.api_stats(db))


@functions_info_router.get("")
def list_functions(db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    rows = db.query(BusinessFunction).filter(BusinessFunction.org_id == user.org_id).order_by(BusinessFunction.sort_order).all()
    out = []
    for f in rows:
        wfs = db.query(Workflow).filter(Workflow.org_id == user.org_id, Workflow.function_key == f.key)
        out.append({"key": f.key, "name": f.name, "description": f.description, "status": f.status, "outcome": f.outcome,
                    "stats": {"total": wfs.count(), "active": wfs.filter(Workflow.status.in_(["pending", "running", "waiting_human"])).count(),
                              "completed": wfs.filter(Workflow.status == "completed").count()} if f.status == "active" else None})
    return out
