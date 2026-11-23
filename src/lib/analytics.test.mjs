import assert from "node:assert/strict";
import { test } from "node:test";
import { barHeights, hoursLabel, money } from "./analytics.js";

test("money formats rupees without decimals and tolerates missing values", () => {
  assert.equal(money(1234567, "INR").replace(/\s/g, ""), "₹12,34,567");
  assert.equal(money(null), "—");
});

test("hoursLabel picks minutes, hours or days", () => {
  assert.equal(hoursLabel(null), "—");
  assert.equal(hoursLabel(0.25), "15 min");
  assert.equal(hoursLabel(5), "5.0 h");
  assert.equal(hoursLabel(72), "3.0 d");
});

test("barHeights scales to the maximum and keeps small values visible", () => {
  assert.deepEqual(barHeights([0, 0]), [0, 0]);
  assert.deepEqual(barHeights([10, 5, 0]), [100, 50, 0]);
  assert.equal(barHeights([1000, 1])[1], 4);
});
