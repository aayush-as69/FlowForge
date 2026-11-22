from app.workflows.types import WorkflowDefinition

DEFINITIONS: dict[str, WorkflowDefinition] = {}


def register(defn: WorkflowDefinition) -> WorkflowDefinition:
    DEFINITIONS[defn.key] = defn
    return defn


def get(key: str) -> WorkflowDefinition:
    if key not in DEFINITIONS:
        # lazy import so function packages self-register
        import app.workflows.procurement  # noqa: F401
    return DEFINITIONS[key]
