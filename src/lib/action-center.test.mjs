import assert from "node:assert/strict";
import { test } from "node:test";
import { ageLabel, filterItems } from "./action-center.js";

const items = [
  { type: "approval", mine: true, overdue: true }, { type: "approval", mine: false, overdue: false },
  { type: "exception", mine: true, overdue: false }, { type: "failed_workflow", mine: false, overdue: true },
];

test("ageLabel is compact and switches to days after two days", () => {
  assert.equal(ageLabel(0.3), "under 1h");
  assert.equal(ageLabel(5.4), "5h");
  assert.equal(ageLabel(47), "47h");
  assert.equal(ageLabel(72), "3d");
});

test("filterItems narrows by tab", () => {
  assert.equal(filterItems(items, "all").length, 4);
  assert.equal(filterItems(items, "mine").length, 2);
  assert.equal(filterItems(items, "overdue").length, 2);
  assert.equal(filterItems(items, "approvals").length, 2);
  assert.equal(filterItems(items, "exceptions").length, 1);
  assert.equal(filterItems(items, "failed").length, 1);
});
