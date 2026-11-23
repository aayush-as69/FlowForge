import assert from "node:assert/strict";
import { test } from "node:test";
import { buildChanges, delta, editableFields } from "./simulator.js";

const policies = [
  { id: 1, params: { max_amount: 50000 } },
  { id: 2, params: { amount: 50000, role: "manager" } },
  { id: 3, params: { categories: ["laptop"] } },
];

test("editableFields lists only numeric params", () => {
  assert.deepEqual(editableFields(policies[0]), ["max_amount"]);
  assert.deepEqual(editableFields(policies[1]), ["amount"]);
  assert.deepEqual(editableFields(policies[2]), []);
});

test("buildChanges keeps only edited policies and merges the untouched params", () => {
  const changes = buildChanges(policies, { 1: { max_amount: "50000" }, 2: { amount: "100000" } });
  assert.deepEqual(changes, [{ policy_id: 2, params: { amount: 100000, role: "manager" } }]);
});

test("buildChanges ignores blank and non-numeric input", () => {
  assert.deepEqual(buildChanges(policies, { 1: { max_amount: "" }, 2: { amount: "abc" } }), []);
  assert.deepEqual(buildChanges(policies, {}), []);
});

test("delta shows a signed difference", () => {
  assert.equal(delta(5, 5), "0");
  assert.equal(delta(5, 8), "+3");
  assert.equal(delta(9, 4), "−5");
});
