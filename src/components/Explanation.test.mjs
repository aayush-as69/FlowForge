import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement as h } from "react";
import { renderToStaticMarkup as html } from "react-dom/server";
import { ExplanationView } from "./Explanation.jsx";

const data = {
  headline: "Completed. Acme was selected.",
  extraction: { engine: "rules", confidence: 0.91, corrected: false },
  policy: { passed: true, results: [{ key: "budget", name: "Budget", status: "pass", label: "passed", message: "Within limit" }, { key: "hr", name: "HR check", status: "fail", label: "failed", message: null }] },
  vendor: { selected: "Acme", reasons: [{ ok: true, text: "Highest overall score" }, { ok: false, text: "Delivery misses the date" }], rejected: [{ vendor: "Zed", eligible: false, why: "Over budget" }] },
  autonomy: { level: 2, plain: "Prepared automatically, then checked by a person", reasons: ["Amount above threshold"] },
  human: [{ approval_id: 1, title: "Manager approval", status: "approved", by: "Meera", role: "manager", note: "ok" }],
  exceptions: [{ code: "ERP_TIMEOUT", message: "ERP timed out", resolution: "Retried" }],
};

test("ExplanationView renders every section from the data", () => {
  const out = html(h(ExplanationView, { data }));
  for (const t of ["Completed. Acme was selected.", "Highest overall score", "Over budget", "Level 2", "approved by Meera (manager)", "ERP_TIMEOUT", "Budget"]) assert.match(out, new RegExp(t.replace(/[()]/g, "\\$&")));
});

test("checks are announced to screen readers, not only coloured", () => {
  const out = html(h(ExplanationView, { data }));
  assert.match(out, /Satisfied:/);
  assert.match(out, /Not satisfied:/);
});

test("ExplanationView omits sections that have no data", () => {
  const out = html(h(ExplanationView, { data: { headline: "In progress.", extraction: null, policy: null, vendor: null, autonomy: null, human: [], exceptions: [] } }));
  assert.match(out, /In progress/);
  assert.doesNotMatch(out, /Policy checks|Why /);
});
