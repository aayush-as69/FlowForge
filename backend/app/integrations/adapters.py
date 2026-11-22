"""Integration layer. Each enterprise system is an adapter behind a small interface.
The MVP ships realistic simulated adapters; a live adapter only needs to implement the same methods
and be registered under the same key (see ADAPTER_CLASSES / INTEGRATION_MODE)."""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import Integration, Vendor


class IntegrationError(Exception):
    code = "INTEGRATION_UNAVAILABLE"


class IntegrationTimeout(IntegrationError):
    code = "INTEGRATION_TIMEOUT"


class IntegrationUnavailable(IntegrationError):
    code = "INTEGRATION_UNAVAILABLE"


def _ref(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8].upper()
    return f"{prefix}-{digest}"


class Adapter:
    key = "base"
    base_latency = 40

    def __init__(self, db: Session | None = None):
        self.db = db

    def health(self) -> dict:
        return {"ok": True, "latency_ms": self.base_latency + (hash(self.key) % 17)}


class ERPAdapter(Adapter):
    key, base_latency = "erp", 120

    def create_purchase_order(self, po: dict, simulate_timeout: bool = False, idempotency_key: str | None = None) -> dict:
        if simulate_timeout:
            raise IntegrationTimeout("ERP did not respond within 5s while posting the purchase order")
        return {"erp_ref": f"ERP-{po['po_number']}", "status": "posted", "gl_account": "5010-IT-HARDWARE", "idempotency_key": idempotency_key}


class AccountingAdapter(Adapter):
    key, base_latency = "accounting", 90

    def check_budget(self, amount: int, cost_center: str) -> dict:
        remaining = 4_800_000
        return {"cost_center": cost_center, "available": amount <= remaining, "remaining": remaining - amount}

    def reserve_commitment(self, po_number: str, amount: int, idempotency_key: str | None = None) -> dict:
        return {"accounting_ref": _ref("ACC", po_number, amount), "status": "committed", "amount": amount, "idempotency_key": idempotency_key}

    def match_invoice(self, po_number: str, amount: int, simulate_mismatch: bool = False) -> dict:
        variance = round(amount * 0.043) if simulate_mismatch else 0
        return {"invoice_ref": _ref("INV", po_number), "matched": variance == 0, "variance": variance,
                "po_total": amount, "invoice_total": amount + variance}

    def release_payment(self, po_number: str, idempotency_key: str | None = None) -> dict:  # destructive: never granted to the agent
        return {"released": True, "idempotency_key": idempotency_key}


class HRAdapter(Adapter):
    key, base_latency = "hr", 70

    def verify_new_hire(self, requester: str, purpose: str) -> dict:
        text = (purpose or "").lower()
        verified = any(k in text for k in ("new employee", "new hire", "joining", "onboard", "new joiner"))
        start = utcnow().date()
        start += timedelta(days=(7 - start.weekday()) % 7 or 7)
        return {"verified": verified, "record": {"employee": "Pending joiner (HRIS #NH-2291)", "start_date": start.isoformat(),
                                                  "department": "Engineering", "equipment_status": "none issued"} if verified else None}


class CRMAdapter(Adapter):
    key, base_latency = "crm", 80

    def get_stakeholder(self, name: str, email: str) -> dict:
        dept = "Engineering"
        return {"name": name, "email": email, "department": dept, "cost_center": "CC-ENG-204",
                "manager": "Meera Iyer", "location": "Bengaluru"}


class EmailAdapter(Adapter):
    key, base_latency = "email", 55

    def send(self, to: str, subject: str, body: str, idempotency_key: str | None = None) -> dict:
        return {"message_id": _ref("MSG", idempotency_key or to, subject), "to": to, "subject": subject, "queued": True, "idempotency_key": idempotency_key}


class VendorDBAdapter(Adapter):
    key, base_latency = "vendor_db", 65

    def search(self, org_id: int, category: str) -> list[dict]:
        rows = self.db.query(Vendor).filter(Vendor.org_id == org_id).order_by(Vendor.id).all()
        return [
            {
                "id": v.id, "name": v.name, "approved": v.approved, "available": v.available,
                "categories": v.categories, "catalog": v.catalog, "historical_avg": v.historical_avg,
                "rating": v.rating, "warranty_years": v.warranty_years, "delivery_days": v.delivery_days,
                "reliability_score": v.reliability_score, "compliance_score": v.compliance_score,
            }
            for v in rows
            if category in (v.catalog or {})
        ]

    def confirm_availability(self, vendor_id: int, simulate_outage: bool = False) -> dict:
        vendor = self.db.get(Vendor, vendor_id)
        ok = bool(vendor and vendor.available) and not simulate_outage
        return {"vendor_id": vendor_id, "available": ok, "stock": "in stock" if ok else "stock-out / outage reported"}

    def confirm_order(self, po_number: str, vendor_id: int, idempotency_key: str | None = None) -> dict:
        vendor = self.db.get(Vendor, vendor_id)
        days = vendor.delivery_days if vendor else 5
        return {"confirmation": _ref("VCF", po_number), "tracking": _ref("TRK", po_number), "eta_days": days, "idempotency_key": idempotency_key,
                "eta_date": (utcnow().date() + timedelta(days=days)).isoformat()}


class DocumentStorageAdapter(Adapter):
    key, base_latency = "documents", 50

    def store(self, name: str, content: str, idempotency_key: str | None = None) -> dict:
        return {"ref": f"doc://flowforge/procurement/{name}#{hashlib.sha1(content.encode()).hexdigest()[:8]}", "bytes": len(content), "idempotency_key": idempotency_key}


ADAPTER_CLASSES: dict[str, type[Adapter]] = {
    "erp": ERPAdapter, "accounting": AccountingAdapter, "hr": HRAdapter, "crm": CRMAdapter,
    "email": EmailAdapter, "vendor_db": VendorDBAdapter, "documents": DocumentStorageAdapter,
}


def get_adapter(db: Session, key: str, org_id: int | None = None) -> Adapter:
    """Return a ready adapter, enforcing the connection state recorded for the integration (of the given organisation)."""
    query = db.query(Integration).filter(Integration.key == key)
    if org_id is not None:
        query = query.filter(Integration.org_id == org_id)
    row = query.first()
    if row is not None:
        if row.status == "disconnected":
            row.failures_total += 1
            db.flush()
            raise IntegrationUnavailable(f"{row.name} is disconnected. Reconnect it in Integrations or retry later.")
        row.calls_total += 1
    return ADAPTER_CLASSES[key](db)


def check_health(db: Session, row: Integration) -> Integration:
    adapter = ADAPTER_CLASSES[row.key](db)
    if row.status == "disconnected":
        row.latency_ms = None
    else:
        info = adapter.health()
        row.latency_ms = info["latency_ms"]
        row.status = "connected" if info["ok"] else "degraded"
    row.last_checked_at = utcnow()
    return row
