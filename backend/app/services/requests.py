from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.agents import extraction
from app.models import Request, User
from app.services import audit as audit_service
from app.workflows import engine as wf_engine
from app.workflows import registry

EDITABLE = ("item", "category", "quantity", "purpose", "required_date", "required_date_text", "budget", "requirements", "requester_name")


def _form_text(fields: dict) -> str:
    lines = ["Purchase Request", "----------------"]
    labels = [("item", "Item"), ("purpose", "Purpose"), ("quantity", "Quantity"), ("required_date_text", "Required date"),
              ("required_date", "Required date"), ("budget", "Budget"), ("requirements", "Additional requirements")]
    seen = set()
    for key, label in labels:
        value = fields.get(key)
        if value in (None, "") or label in seen:
            continue
        seen.add(label)
        lines.append(f"{label}: {'₹' + format(value, ',') if key == 'budget' else value}")
    return "\n".join(lines)


def create_request(db: Session, user: User, *, text: str | None, fields: dict | None, source: str,
                   demo_faults: list[str] | None = None, is_demo: bool = False, requester: User | None = None,
                   today: date | None = None) -> Request:
    fields = {k: v for k, v in (fields or {}).items() if v not in (None, "")}
    raw = text.strip() if text else _form_text(fields)
    result = extraction.extract(raw, today)
    data = result.fields.model_dump()
    for key, value in fields.items():  # structured form input always wins over inferred values
        data[key] = value
    if not data.get("category") and data.get("item"):
        data["category"] = extraction.classify(data["item"])
    owner = requester or user
    req = Request(
        org_id=owner.org_id, requester_id=owner.id, function_key="procurement", source=source, raw_text=raw,
        status="extracted", confidence=result.confidence, extraction_engine=result.engine,
        extraction_notes=result.notes, demo_faults=demo_faults or [], is_demo=is_demo, **{k: data.get(k) for k in EDITABLE},
    )
    db.add(req)
    db.flush()
    audit_service.record(db, org_id=owner.org_id, workflow_id=None, actor_type="user", actor=user.name, action="request.submitted",
                         input={"source": source, "text": raw[:300]}, output={"request_id": req.id}, status="submitted")
    audit_service.record(db, org_id=owner.org_id, workflow_id=None, actor_type="ai", actor=f"Extraction Agent ({result.engine})",
                         action="request.extracted", input={"request_id": req.id},
                         output={k: data.get(k) for k in EDITABLE}, reason=f"Confidence {int(result.confidence * 100)}%",
                         status="understood")
    db.commit()
    return req


def update_request(db: Session, req: Request, patch: dict, user: User) -> Request:
    for key, value in patch.items():
        if key in EDITABLE:
            setattr(req, key, value)
    if "category" in patch and patch["category"]:
        req.category = patch["category"].lower().strip()
    req.corrected = True
    audit_service.record(db, org_id=req.org_id, workflow_id=None, actor_type="user", actor=user.name, action="request.corrected",
                         input={"request_id": req.id}, output=patch, reason="Human corrected extracted data before execution",
                         status="corrected")
    db.commit()
    return req


def missing_fields(req: Request) -> list[str]:
    return [f for f in ("category", "quantity", "budget") if not getattr(req, f)]


def start_workflow(db: Session, req: Request, user: User, *, is_demo: bool = False, step_delay: float | None = None):
    definition = registry.get("procurement.standard")
    qty = req.quantity or 1
    title = f"{qty}× {req.item or req.category} for {req.requester_name or req.requester.name}"
    wf = wf_engine.create_workflow(
        db, definition, org_id=req.org_id, title=title, request=req, created_by=user.id, is_demo=is_demo,
        step_delay=step_delay, context={"faults": req.demo_faults, "faults_consumed": [], "overrides": {}})
    req.status = "executing"
    db.commit()
    return wf
