"""Shared building blocks for every business-function workflow."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services import audit as audit_service


class FlowException(Exception):
    """Raised by step handlers. Never terminates a workflow directly: the exception engine decides."""

    def __init__(self, code: str, message: str, details: dict | None = None, recoverable: bool | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.recoverable = recoverable


@dataclass
class ApprovalSpec:
    title: str
    summary: str  # what happened
    reason: str  # why a human is needed
    recommendation: str
    risk: str = ""
    risk_level: str = "medium"
    supporting_data: dict = field(default_factory=dict)
    assigned_role: str = "approver"
    level: int = 2
    kind: str = "approval"  # approval | exception_review
    options: list[str] = field(default_factory=lambda: ["approve", "reject", "modify", "escalate"])


@dataclass
class StepResult:
    status: str = "completed"  # completed | skipped | wait_human
    output: dict = field(default_factory=dict)
    decision: str | None = None
    reason: str | None = None
    approval: ApprovalSpec | None = None
    ctx_patch: dict = field(default_factory=dict)


@dataclass
class StepDef:
    key: str
    name: str
    handler: Callable[["StepContext"], StepResult]
    kind: str = "automated"  # automated | decision | approval
    action: str = ""
    input_fn: Callable[["StepContext"], dict] | None = None
    allowed_tools: tuple[str, ...] = ()


@dataclass
class WorkflowDefinition:
    key: str
    function_key: str
    name: str
    steps: list[StepDef]
    agent_scopes: frozenset[str] = frozenset()
    completion_criteria: Callable[[Session, Any], list[str]] = lambda db, wf: []
    plan_fn: Callable[[Any], list[dict]] | None = None

    def step(self, key: str) -> StepDef:
        for s in self.steps:
            if s.key == key:
                return s
        raise KeyError(key)


class StepContext:
    """What a step handler can see and do. Everything goes through here so it is audited."""

    def __init__(self, db: Session, workflow, step, definition: WorkflowDefinition, sdef: StepDef):
        self.db = db
        self.workflow = workflow
        self.step = step
        self.definition = definition
        self.sdef = sdef

    @property
    def request(self):
        return self.workflow.request

    @property
    def ctx(self) -> dict:
        return dict(self.workflow.context or {})

    @property
    def overrides(self) -> dict:
        return dict(self.ctx.get("overrides", {}))

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        return self.sdef.allowed_tools

    def set(self, **patch) -> None:
        self.workflow.context = {**(self.workflow.context or {}), **audit_service.json_safe(patch)}

    def override(self, **patch) -> None:
        self.set(overrides={**self.overrides, **patch})

    def consume_fault(self, name: str) -> bool:
        """Demo fault injection: a fault fires once per workflow, then is marked consumed."""
        ctx = self.ctx
        if name in ctx.get("faults", []) and name not in ctx.get("faults_consumed", []):
            self.set(faults_consumed=[*ctx.get("faults_consumed", []), name])
            return True
        return False

    def audit(self, action: str, *, actor_type: str = "system", actor: str = "FlowForge Engine", **kw):
        return audit_service.record(
            self.db, org_id=self.workflow.org_id, workflow_id=self.workflow.id,
            actor_type=actor_type, actor=actor, action=action, **kw,
        )

    def tool(self, tool_name: str, /, **args):
        from app.agents.tools import call_tool

        return call_tool(self, tool_name, **args)
