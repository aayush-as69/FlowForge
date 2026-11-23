import assert from "node:assert/strict";
import { test } from "node:test";
import { duration, fmtDate, inr, relTime, titleCase } from "./format.js";

test("inr formats rupees with Indian grouping and handles missing values", () => {
  assert.equal(inr(100000), "₹1,00,000");
  assert.equal(inr(1234.6), "₹1,235");
  assert.equal(inr(0), "₹0");
  assert.equal(inr(null), "—");
  assert.equal(inr(undefined), "—");
});

test("duration picks a readable unit", () => {
  assert.equal(duration(null), "—");
  assert.equal(duration(250), "250 ms");
  assert.equal(duration(1500), "1.5 s");
  assert.equal(duration(180000), "3 min");
});

test("relTime buckets elapsed time", () => {
  const ago = (s) => new Date(Date.now() - s * 1000).toISOString();
  assert.equal(relTime(null), "—");
  assert.equal(relTime(ago(5)), "just now");
  assert.equal(relTime(ago(10 * 60)), "10m ago");
  assert.equal(relTime(ago(3 * 3600)), "3h ago");
  assert.equal(relTime(ago(2 * 86400)), "2d ago");
  assert.equal(relTime(new Date(Date.now() + 60000).toISOString()), "just now"); // clock skew never shows negative time
});

test("fmtDate treats date-only strings as local calendar days", () => {
  assert.match(fmtDate("2026-03-05"), /05 Mar,? 2026/);
  assert.equal(fmtDate(null), "—");
});

test("titleCase turns identifiers into labels", () => {
  assert.equal(titleCase("waiting_human"), "Waiting Human");
  assert.equal(titleCase(""), "");
  assert.equal(titleCase(undefined), "");
});
