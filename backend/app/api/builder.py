"""Workflow Builder API: templates, versioned definitions, test mode and running a published workflow."""
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.core.db import get_db, utcnow
from app.core.security import require
from app.models import WorkflowDefinitionRecord as Rec
from app.services import audit as audit_service
from app.services import builder, runner
from app.services.builder_templates import BY_KEY, TEMPLATES
from app.workflows import engine as wf_engine
from app.workflows import registry

router = APIRouter(prefix="/builder", tags=["builder"])


class DefinitionIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=1000)
    key: str | None = Field(default=None, max_length=60)
    template_key: str | None = None
    spec: dict | None = None
    tests: list | None = None


class DefinitionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    spec: dict | None = None
    tests: list | None = None


class TestIn(BaseModel):
    spec: dict
    text: str | None = Field(default=None, max_length=4000)
    fields: dict | None = None


class RunIn(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    fields: dict | None = None


def _ser(r: Rec, full: bool = True) -> dict:
    out = {"id": r.id, "key": r.key, "version": r.version, "name": r.name, "description": r.description,
           "status": r.status, "template_key": r.template_key, "steps": len((r.spec or {}).get("steps", [])),
           "tests": len(r.tests or []), "created_at": r.created_at, "published_at": r.published_at}
    if full:
        out.update(spec=r.spec, test_cases=r.tests)
    return out


def _get(db: Session, user, rid: int) -> Rec:
    r = db.get(Rec, rid)
    if r is None or r.org_id != user.org_id:
        raise HTTPException(404, "Workflow definition not found.")
    return r


def _check(spec, tests):
    problems = builder.validate_spec(spec) + builder.validate_tests(tests)
    if problems:
        raise HTTPException(422, {"message": "The workflow is not valid.", "problems": problems})


def _audit(db, user, action, r, reason=""):
    audit_service.record(db, org_id=user.org_id, workflow_id=None, actor_type="user", actor=user.name, action=action,
                         input={"definition_id": r.id, "key": r.key, "version": r.version}, reason=reason, status=r.status)


@router.get("/templates")
def templates(user=Depends(require("workflows:read"))):
    return [{"key": t["key"], "name": t["name"], "description": t["description"], "steps": len(t["spec"]["steps"]),
             "tests": len(t["tests"]), "spec": t["spec"], "test_cases": t["tests"]} for t in TEMPLATES]


@router.get("/definitions")
def list_definitions(db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    rows = db.query(Rec).filter(Rec.org_id == user.org_id).order_by(Rec.key, Rec.version.desc()).all()
    groups: dict[str, list[Rec]] = {}
    for r in rows:
        groups.setdefault(r.key, []).append(r)
    items = []
    for key, versions in groups.items():
        published = next((v for v in versions if v.status == "published"), None)
        head = published or versions[0]
        items.append({**_ser(head, full=False), "versions": [_ser(v, full=False) for v in versions],
                      "runnable": published is not None})
    return {"items": sorted(items, key=lambda i: i["name"].lower())}


@router.post("/definitions", status_code=201)
def create_definition(body: DefinitionIn, db: Session = Depends(get_db), user=Depends(require("policies:write"))):
    spec, tests, tpl = body.spec, body.tests, body.template_key
    if tpl:
        if tpl not in BY_KEY:
            raise HTTPException(422, f"Unknown template '{tpl}'.")
        spec = spec or BY_KEY[tpl]["spec"]
        tests = tests if tests is not None else BY_KEY[tpl]["tests"]
    spec = spec or {"steps": [{"id": "understand", "type": "extract", "name": "Understand the request"}]}
    tests = tests or []
    _check(spec, tests)
    key = (body.key or re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-"))[:60]
    if not builder.KEY_RE.match(key):
        raise HTTPException(422, "Key must be lowercase letters, digits or '-' (2–60 characters, starting with a letter).")
    if db.query(Rec).filter(Rec.org_id == user.org_id, Rec.key == key).first():
        raise HTTPException(409, f"A workflow with the key '{key}' already exists — open it and create a new version.")
    r = Rec(org_id=user.org_id, key=key, version=1, name=body.name.strip(), description=body.description, spec=spec,
            tests=tests, template_key=tpl, created_by=user.id, status="draft")
    db.add(r)
    db.flush()
    _audit(db, user, "builder.created", r, f"Draft created{' from template ' + tpl if tpl else ''}")
    db.commit()
    return _ser(r)


@router.get("/definitions/{rid}")
def get_definition(rid: int, db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    return _ser(_get(db, user, rid))


@router.put("/definitions/{rid}")
def update_definition(rid: int, body: DefinitionPatch, db: Session = Depends(get_db),
                      user=Depends(require("policies:write"))):
    r = _get(db, user, rid)
    if r.status != "draft":
        raise HTTPException(409, "Only a draft can be edited. Create a new version to change a published workflow.")
    spec = body.spec if body.spec is not None else r.spec
    tests = body.tests if body.tests is not None else r.tests
    _check(spec, tests)
    if body.name is not None:
        r.name = body.name.strip()
    if body.description is not None:
        r.description = body.description
    r.spec, r.tests = spec, tests
    _audit(db, user, "builder.updated", r, "Draft edited")
    db.commit()
    return _ser(r)


@router.post("/definitions/{rid}/new-version", status_code=201)
def new_version(rid: int, db: Session = Depends(get_db), user=Depends(require("policies:write"))):
    src = _get(db, user, rid)
    if src.status == "draft":
        raise HTTPException(409, "This version is still a draft — edit it directly.")
    if db.query(Rec).filter(Rec.org_id == user.org_id, Rec.key == src.key, Rec.status == "draft").first():
        raise HTTPException(409, "There is already a draft for this workflow — finish or discard it first.")
    top = db.query(func.max(Rec.version)).filter(Rec.org_id == user.org_id, Rec.key == src.key).scalar() or 0
    r = Rec(org_id=user.org_id, key=src.key, version=top + 1, name=src.name, description=src.description,
            spec=src.spec, tests=src.tests, template_key=src.template_key, created_by=user.id, status="draft")
    db.add(r)
    db.flush()
    _audit(db, user, "builder.version_created", r, f"New draft based on v{src.version}")
    db.commit()
    return _ser(r)


@router.post("/definitions/{rid}/tests/run")
def run_saved_tests(rid: int, db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    r = _get(db, user, rid)
    return builder.run_tests(r.spec, r.tests)


@router.post("/definitions/{rid}/publish")
def publish(rid: int, db: Session = Depends(get_db), user=Depends(require("policies:write"))):
    r = _get(db, user, rid)
    if r.status != "draft":
        raise HTTPException(409, "Only a draft can be published.")
    _check(r.spec, r.tests)
    if not r.tests:
        raise HTTPException(422, {"message": "Add at least one test case before publishing.", "problems": ["no test cases"]})
    result = builder.run_tests(r.spec, r.tests)
    if result["failed"]:
        raise HTTPException(422, {"message": f"{result['failed']} test case(s) are failing, so this version cannot be published.",
                                  "problems": [f"{x['name']}: expected {x['expected']}, got {x['actual']}" for x in result["results"] if not x["passed"]]})
    for old in db.query(Rec).filter(Rec.org_id == user.org_id, Rec.key == r.key, Rec.status == "published").all():
        old.status = "archived"  # stays resolvable: running workflows keep the version they started on
    r.status, r.published_at = "published", utcnow()
    _audit(db, user, "builder.published", r, f"Published after {result['total']} passing test case(s)")
    db.commit()
    return _ser(r)


@router.post("/definitions/{rid}/archive")
def archive(rid: int, db: Session = Depends(get_db), user=Depends(require("policies:write"))):
    r = _get(db, user, rid)
    if r.status == "archived":
        return _ser(r)
    r.status = "archived"
    _audit(db, user, "builder.archived", r, "No longer available for new runs")
    db.commit()
    return _ser(r)


@router.post("/test")
def test_mode(body: TestIn, user=Depends(require("workflows:read"))):
    if not (body.text and body.text.strip()) and not body.fields:
        raise HTTPException(422, "Give some request text or fields to test with.")
    try:
        return builder.dry_run(body.spec, body.text, body.fields)
    except builder.SpecError as e:
        raise HTTPException(422, {"message": "The workflow is not valid.", "problems": e.problems})


@router.post("/definitions/{rid}/run", status_code=201)
def run_definition(rid: int, body: RunIn, bg: BackgroundTasks, db: Session = Depends(get_db),
                   user=Depends(require("workflows:operate"))):
    r = _get(db, user, rid)
    if r.status != "published":
        raise HTTPException(409, "Only a published version can be run.")
    if not (body.text and body.text.strip()) and not body.fields:
        raise HTTPException(422, "Give some request text or fields.")
    definition = registry.get(f"custom:{r.id}", db)
    label = (body.text or "").strip().splitlines()[0][:70] if (body.text or "").strip() else "structured input"
    wf = wf_engine.create_workflow(
        db, definition, org_id=user.org_id, title=f"{r.name}: {label}", created_by=user.id,
        context={"input": {"text": body.text, "fields": body.fields or {}}, "overrides": {}, "faults": [],
                 "faults_consumed": [], "definition": {"id": r.id, "key": r.key, "version": r.version}})
    audit_service.record(db, org_id=user.org_id, workflow_id=wf.id, actor_type="user", actor=user.name,
                         action="workflow.submitted", input={"definition": f"{r.key} v{r.version}"}, status="submitted")
    db.commit()
    bg.add_task(runner.submit, wf.id)
    return ser.ser_workflow(wf)
