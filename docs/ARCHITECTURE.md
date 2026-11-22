# Architecture

```
Browser ──► Next.js (JSX UI, /api/health, proxy)  ──/api/*──►  FastAPI (Python)  ──► PostgreSQL (schema "flowforge")
                 │ instrumentation.js supervises ───────────────┘
```

`backend/app` (Python 3.11, FastAPI, SQLAlchemy, Pydantic):

| Package | Responsibility |
|---|---|
| `workflows/engine.py` | Reusable engine: steps, states (pending, running, completed, failed, waiting_human, resolved, skipped), conditions (skips), persisted context, approvals, completion criteria, rewind, retry, resume |
| `workflows/procurement.py` | The *only* procurement-specific code: step handlers, exception specs, resolvers, definition |
| `services/policy_engine.py` | Interprets policy rows (`rule_type` + params). Pure functions |
| `decisions/engine.py` | Level 1/2/3 autonomy decision from facts + policy report + configurable thresholds, with a rule trace |
| `exceptions/engine.py` | detect → classify → recoverable? → retry → auto-resolve (resolvers) → escalate to human → record → resume |
| `services/approvals.py` | Human-in-the-loop: approve / reject / modify / escalate, RBAC + separation of duties, then workflow resume |
| `agents/` | `extraction` (LLM with strict JSON + deterministic fallback), `planner`, `explain`, `llm` client, `tools` (explicit tool registry) |
| `integrations/adapters.py` | ERP, CRM, Email, Vendor DB, HR, Accounting, Document storage adapters (simulated; swap for live clients) |
| `services/audit.py` | Append-only audit events for every important action |
| `services/runner.py` | Background execution (thread pool), resume of interrupted workflows on start-up |

**AI vs deterministic code.** AI proposes (extraction, plan, explanations, rationale). Deterministic Python decides and enforces
(auth, RBAC, policies, thresholds, state, audit). The AI layer can only act through registered tools; each call is checked against the
step's allow-list, the agent's granted scopes, and a hard block on destructive tools (`accounting.release_payment` is never granted).

**Adding a function.** Create a `WorkflowDefinition` (steps + handlers), register `ExceptionSpec`s, add policy rows. The engine,
decision/exception/approval/policy/audit services and the UI (graph, inspector, approval center) are reused unchanged.

**Demo simulation.** `demo_faults` (`erp_timeout`, `vendor_unavailable`, `invoice_mismatch`) make a mock adapter fail once per workflow so
the exception engine can be demonstrated. The price anomaly in the primary demo is *not* simulated: it emerges from vendor data
(Bluepeak quotes ₹91,000 vs a ₹77,100 historical average = +18%).

**Without an LLM key** extraction uses a rule-based parser and says so (`extraction_engine = heuristic`). Set `LLM_API_KEY` to use an LLM.
