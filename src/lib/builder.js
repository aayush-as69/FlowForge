// Pure helpers for the workflow builder UI (kept out of page files: Next pages may not export extra names).
export const STEP_TYPES = {
  extract: { label: "Understand request", hint: "Reads the request text into fields such as item, quantity and amount." },
  rule: { label: "Policy check", hint: "Checks conditions. If they fail, flag the case for approval or block it for review." },
  approval: { label: "Human approval", hint: "Waits for a person with at least the chosen role." },
  notify: { label: "Notify", hint: "Records a notification in the audit trail (nothing is sent externally)." },
};
export const FIELDS = ["amount", "quantity", "category", "item", "purpose", "requirements", "required_date_text", "text"];
export const NUMERIC = ["amount", "quantity"];
export const ROLES = ["approver", "manager", "admin"];
export const OUTCOMES = { auto: "Runs automatically", approval: "Needs approval", blocked: "Blocked for review" };

export function opsFor(field) {
  return NUMERIC.includes(field) ? ["<=", "<", ">=", ">", "==", "!=", "exists"] : ["==", "!=", "in", "contains", "exists"];
}

export function uniqueId(steps, base) {
  const used = new Set(steps.map((s) => s.id));
  if (!used.has(base)) return base;
  let n = 2;
  while (used.has(`${base}_${n}`)) n += 1;
  return `${base}_${n}`;
}

export function newStep(type, steps) {
  const id = uniqueId(steps, type === "extract" ? "understand" : type);
  const name = STEP_TYPES[type].label;
  if (type === "rule") return { id, type, name, on_fail: "approval", message: "", conditions: [{ field: "amount", op: "<=", value: 0 }] };
  if (type === "approval") return { id, type, name, role: "manager", when: "always" };
  if (type === "notify") return { id, type, name, message: "" };
  return { id, type, name };
}

export function moveStep(steps, index, dir) {
  const to = index + dir;
  if (to < 0 || to >= steps.length) return steps;
  const next = steps.slice();
  [next[index], next[to]] = [next[to], next[index]];
  return next;
}

export const removeStep = (steps, index) => steps.filter((_, i) => i !== index);
export const patchStep = (steps, index, patch) => steps.map((s, i) => (i === index ? { ...s, ...patch } : s));

// A condition's value is typed from the field/operator so the API never receives "500" where it needs 500.
export function coerceValue(field, op, raw) {
  if (op === "exists") return undefined;
  if (op === "in") return String(raw ?? "").split(",").map((x) => x.trim()).filter(Boolean);
  if (NUMERIC.includes(field)) {
    const n = Number(String(raw ?? "").replace(/,/g, ""));
    return raw === "" || Number.isNaN(n) ? raw : n;
  }
  if ((op === "==" || op === "!=") && raw !== "" && !Number.isNaN(Number(raw))) return Number(raw);
  return raw;
}

export function patchCondition(step, ci, patch) {
  const conditions = step.conditions.map((c, i) => {
    if (i !== ci) return c;
    const next = { ...c, ...patch };
    if (patch.field && !opsFor(patch.field).includes(next.op)) next.op = opsFor(patch.field)[0];
    if ("value" in patch || patch.field || patch.op) {
      const raw = "value" in patch ? patch.value : c.value;
      const v = coerceValue(next.field, next.op, Array.isArray(raw) ? raw.join(", ") : raw);
      if (v === undefined) delete next.value; else next.value = v;
    }
    return next;
  });
  return { ...step, conditions };
}

export function describeStep(s) {
  if (s.type === "rule") {
    const c = (s.conditions || []).map((x) => `${x.field} ${x.op}${x.op === "exists" ? "" : ` ${Array.isArray(x.value) ? x.value.join("/") : x.value}`}`).join(" and ");
    return `${c || "no conditions"} → otherwise ${s.on_fail === "block" ? "block for review" : "flag for approval"}`;
  }
  if (s.type === "approval") return `${s.when === "flagged" ? "Only if flagged" : "Always"} · ${s.role}`;
  if (s.type === "notify") return s.message || "no message";
  return STEP_TYPES[s.type]?.hint || "";
}

// Validation failures carry a list of problems; anything else is shown as its message.
export function problemsOf(err) {
  if (Array.isArray(err?.problems) && err.problems.length) return err.problems;
  return [err?.message || "Something went wrong."];
}

export function newTestCase(n) {
  return { name: `Case ${n}`, text: "", fields: { amount: 1000 }, expect: { outcome: "auto" } };
}

export function statusTone(status) {
  return { published: "green", draft: "amber", archived: "slate" }[status] || "slate";
}
