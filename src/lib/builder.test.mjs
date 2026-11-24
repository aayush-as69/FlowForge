import assert from "node:assert/strict";
import { test } from "node:test";
import { coerceValue, describeStep, moveStep, newStep, opsFor, patchCondition, patchStep, problemsOf, removeStep, uniqueId } from "./builder.js";

test("new steps get unique ids and sensible defaults", () => {
  const steps = [newStep("extract", [])];
  assert.equal(steps[0].id, "understand");
  const a = newStep("rule", steps);
  const b = newStep("rule", [...steps, a]);
  assert.deepEqual([a.id, b.id], ["rule", "rule_2"]);
  assert.equal(a.on_fail, "approval");
  assert.deepEqual(newStep("approval", []), { id: "approval", type: "approval", name: "Human approval", role: "manager", when: "always" });
  assert.equal(uniqueId([{ id: "x" }, { id: "x_2" }], "x"), "x_3");
});

test("reordering and removing never mutate the original list", () => {
  const steps = [{ id: "a" }, { id: "b" }, { id: "c" }];
  assert.deepEqual(moveStep(steps, 0, 1).map((s) => s.id), ["b", "a", "c"]);
  assert.deepEqual(moveStep(steps, 0, -1), steps);
  assert.deepEqual(moveStep(steps, 2, 1), steps);
  assert.deepEqual(removeStep(steps, 1).map((s) => s.id), ["a", "c"]);
  assert.deepEqual(patchStep(steps, 1, { name: "B" })[1], { id: "b", name: "B" });
  assert.deepEqual(steps.map((s) => s.id), ["a", "b", "c"]);
});

test("condition values are typed from the field and operator", () => {
  assert.equal(coerceValue("amount", "<=", "5,000"), 5000);
  assert.equal(coerceValue("amount", "<=", ""), "");
  assert.deepEqual(coerceValue("category", "in", "laptop, monitor ,"), ["laptop", "monitor"]);
  assert.equal(coerceValue("category", "==", "laptop"), "laptop");
  assert.equal(coerceValue("item", "exists", "x"), undefined);
});

test("changing the field switches to an operator that field supports", () => {
  assert.deepEqual(opsFor("amount").includes("in"), false);
  assert.deepEqual(opsFor("category").includes("<="), false);
  const step = { conditions: [{ field: "amount", op: "<=", value: 100 }] };
  const next = patchCondition(step, 0, { field: "category" });
  assert.equal(next.conditions[0].op, "==");
  assert.equal(step.conditions[0].field, "amount");
  const ex = patchCondition(step, 0, { op: "exists" });
  assert.equal("value" in ex.conditions[0], false);
  assert.equal(patchCondition(step, 0, { value: "250" }).conditions[0].value, 250);
});

test("steps are described in plain words", () => {
  assert.match(describeStep({ type: "rule", on_fail: "block", conditions: [{ field: "category", op: "in", value: ["a", "b"] }] }), /category in a\/b → otherwise block for review/);
  assert.equal(describeStep({ type: "approval", role: "admin", when: "flagged" }), "Only if flagged · admin");
});

test("validation problems are listed, other errors fall back to the message", () => {
  assert.deepEqual(problemsOf({ problems: ["a", "b"], message: "x" }), ["a", "b"]);
  assert.deepEqual(problemsOf(new Error("boom")), ["boom"]);
  assert.deepEqual(problemsOf(null), ["Something went wrong."]);
});
