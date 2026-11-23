import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { createElement as h } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import AuthProvider from "../../components/AuthProvider.jsx";
import Audit from "../(app)/audit/page.jsx";
import Procurement from "../(app)/functions/procurement/page.jsx";
import { mockFetch } from "../../test/helpers.mjs";

afterEach(cleanup);

const user = (role) => ({ id: 1, name: "Test", email: `${role}@x.test`, role });
const EMPTY_PAGE = { items: [], page: 1, pages: 1, total: 0 };

test("audit page shows a verified badge with the event count", async () => {
  mockFetch({ "GET /audit?*": EMPTY_PAGE, "GET /audit/verify": { ok: true, checked: 42, problem_count: 0, problems: [], forks: 0 } });
  render(h(Audit));
  await waitFor(() => assert.ok(screen.getByText(/Hash chain verified · 42 events/)));
});

test("audit page shows a red warning when the chain is broken", async () => {
  mockFetch({ "GET /audit?*": EMPTY_PAGE, "GET /audit/verify": { ok: false, checked: 10, problem_count: 2, problems: [], forks: 0 } });
  render(h(Audit));
  await waitFor(() => assert.ok(screen.getByText(/Chain broken · 2 problem\(s\)/)));
  assert.equal(screen.queryByText(/Hash chain verified/), null);
});

test("audit page still renders if verification is unavailable", async () => {
  mockFetch({ "GET /audit?*": EMPTY_PAGE });
  render(h(Audit));
  await waitFor(() => assert.ok(screen.getByText(/No audit events match/)));
  assert.equal(screen.queryByText(/Hash chain/), null);
});

function procurement(role, permissions) {
  return mockFetch({
    "GET /auth/me": { user: user(role), permissions },
    "GET /functions/procurement/scenarios": [{ key: "routine", label: "Keyboard sets", text: "Need 5 sets", shows: ["Level 1"] }],
  });
}

test("procurement shows demo controls only to users who hold demo:run", async () => {
  const calls = procurement("manager", ["requests:create", "workflows:read", "demo:run"]);
  render(h(AuthProvider, null, h(Procurement)));
  await waitFor(() => assert.ok(screen.getByText(/Run the primary demo/)));
  assert.ok(screen.getByText(/Guided demo scenarios/));
  assert.ok(calls.some((c) => c.key === "GET /functions/procurement/scenarios"));
});

test("procurement hides every demo control, and never loads scenarios, without demo:run", async () => {
  const calls = procurement("requester", ["requests:create", "workflows:read"]);
  render(h(AuthProvider, null, h(Procurement)));
  await waitFor(() => assert.ok(screen.getByText(/Understand request/)));
  assert.equal(screen.queryByText(/Run the primary demo/), null);
  assert.equal(screen.queryByText(/Guided demo scenarios/), null);
  assert.equal(screen.queryByText(/Demo simulation options/), null);
  assert.ok(!calls.some((c) => c.key.includes("scenarios")));
});

import ActionCenter from "../(app)/action-center/page.jsx";

test("action center lists items, defaulting to the ones that need me", async () => {
  mockFetch({ "GET /action-center": { counts: { mine: 1, overdue: 1, approvals: 1, exceptions: 1, failed: 0 }, items: [
    { type: "approval", id: 1, workflow_id: 5, workflow_ref: "WF-1005", title: "Laptop purchase", summary: "Needs manager", age_hours: 30, overdue: true, mine: true },
    { type: "exception", id: 2, workflow_id: 6, workflow_ref: "WF-1006", title: "Monitors", summary: "Vendor timeout", age_hours: 2, overdue: false, mine: false },
  ] } });
  render(h(ActionCenter));
  await waitFor(() => assert.ok(screen.getByText("Laptop purchase")));
  assert.ok(screen.getByText(/Overdue · 30h/));
  assert.equal(screen.queryByText("Monitors"), null); // not mine, hidden on the default tab
});

test("action center shows an empty state when nothing needs a person", async () => {
  mockFetch({ "GET /action-center": { counts: { mine: 0, overdue: 0, approvals: 0, exceptions: 0, failed: 0 }, items: [] } });
  render(h(ActionCenter));
  await waitFor(() => assert.ok(screen.getByText("All clear")));
});

import Analytics from "../(app)/analytics/page.jsx";

const OVERVIEW = {
  window_days: 30, volume: { started: 40, completed: 30, failed: 2, cancelled: 0, in_progress: 8 },
  rates: { success_pct: 93.8, automation_pct: 60, human_intervention_pct: 40, exception_pct: 12.5 }, avg_duration_s: 12,
  approval_latency: { decided: 12, avg_hours: 6.5, median_hours: 4, slowest_role: { role: "manager", count: 5, avg_hours: 18.4 },
    by_role: [{ role: "manager", count: 5, avg_hours: 18.4 }, { role: "approver", count: 7, avg_hours: 0.5 }] },
  failure_reasons: [{ code: "ERP_TIMEOUT", count: 5, recovered: 4 }],
  daily: [{ date: "2026-11-01", completed: 3 }, { date: "2026-11-02", completed: 0 }],
  roi: { currency: "INR", manual_cost: 22500, ai_cost: 45, api_cost: 60, human_cost: 480, total_cost: 585, savings: 21915, hours_saved: 36.2,
    assumptions: { manual_minutes_per_request: 45, hourly_cost: 600, human_review_minutes: 8, llm_call_cost: 1.5, tool_call_cost: 0.2 } },
};

test("analytics page shows the headline numbers, the bottleneck role and the stated assumptions", async () => {
  const calls = mockFetch({ "GET /analytics/overview?*": OVERVIEW });
  render(h(Analytics));
  await waitFor(() => assert.ok(screen.getByText("Workflows started")));
  assert.ok(screen.getByText("Slowest: manager"));
  assert.ok(screen.getByText("ERP_TIMEOUT"));
  assert.ok(screen.getByText(/estimate from the assumptions below, not billing data/i));
  assert.match(screen.getByText(/min of manual work per request/).textContent, /45 min of manual work per request at/);
  assert.ok(calls[0].key.includes("days=30"));
});
