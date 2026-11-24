from app.workflows.types import WorkflowDefinition

DEFINITIONS: dict[str, WorkflowDefinition] = {}


def register(defn: WorkflowDefinition) -> WorkflowDefinition:
    DEFINITIONS[defn.key] = defn
    return defn


def get(key: str, db=None) -> WorkflowDefinition:
    """Built-in definitions are code; "custom:<id>" keys are rebuilt from the exact stored version they were started on."""
    if key.startswith("custom:"):
        from app.models import WorkflowDefinitionRecord
        from app.services import builder

        record = db.get(WorkflowDefinitionRecord, int(key.split(":", 1)[1])) if db is not None else None
        if record is None:
            raise KeyError(key)
        return builder.build_definition(record)
    if key not in DEFINITIONS:
        # lazy import so function packages self-register
        import app.workflows.procurement  # noqa: F401
    return DEFINITIONS[key]
