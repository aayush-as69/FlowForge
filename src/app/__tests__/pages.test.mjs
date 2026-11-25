import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { createElement as h } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import AuthProvider from "../../components/AuthProvider.jsx";
import Audit from "../(app)/audit/page.jsx";
import Procurement from "../(app)/functions/procurement/page.jsx";
import { mockFetch, status } from "../../test/helpers.mjs";

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

import { fireEvent } from "@testing-library/react";
import Simulator from "../(app)/policies/simulator/page.jsx";

const POLICIES = [{ id: 7, name: "Autonomous limit", description: "Largest order that runs alone", params: { max_amount: 50000 }, severity: "block", enabled: true }];
const SIM = { mode: "history", sampled: 40, replayed: 38, skipped: 2, current: { auto: 10, review: 20, human: 5, blocked: 2, exception: 1, needs_human: 28 },
  proposed: { auto: 20, review: 10, human: 5, blocked: 2, exception: 1, needs_human: 17 }, human_workload_change_pct: 35.7, changed_count: 10,
  changed: [{ workflow_id: 3, ref: "WF-1003", title: "Monitors", amount: 80000, before: "review", after: "auto" }] };

test("simulator is limited to administrators", async () => {
  mockFetch({ "GET /auth/me": { user: user("manager"), permissions: ["policies:read"] }, "GET /policies": POLICIES });
  render(h(AuthProvider, null, h(Simulator)));
  await waitFor(() => assert.ok(screen.getByText(/Only administrators can use the policy simulator/)));
});

test("simulator sends only the edited policy and shows the before/after table", async () => {
  const calls = mockFetch({ "GET /auth/me": { user: user("admin"), permissions: ["policies:write"] }, "GET /policies": POLICIES, "POST /policies/simulate": SIM });
  render(h(AuthProvider, null, h(Simulator)));
  const input = await waitFor(() => screen.getByDisplayValue("50000"));
  const button = screen.getByText("Test against history");
  assert.equal(button.disabled, true); // nothing changed yet
  fireEvent.change(input, { target: { value: "100000" } });
  await waitFor(() => assert.equal(screen.getByText("Test against history").disabled, false));
  fireEvent.click(screen.getByText("Test against history"));
  await waitFor(() => assert.ok(screen.getByText(/Replayed 38 past workflows/)));
  assert.deepEqual(calls.find((c) => c.key === "POST /policies/simulate").body, { changes: [{ policy_id: 7, params: { max_amount: 100000 } }], sample: 500 });
  assert.ok(screen.getByText(/Estimated human workload change: −35.7%/));
  assert.ok(screen.getByText("−11")); // needs-a-person row: 28 → 17
});

import BuilderHome from "../(app)/builder/page.jsx";
import BuilderEditor from "../(app)/builder/[id]/page.jsx";
import { navigations, params } from "../../test/next-navigation-stub.mjs";

const DEF_ROW = { id: 5, key: "expense", version: 2, name: "Expense approval", description: "", status: "published", steps: 4, tests: 3, runnable: true,
  versions: [{ id: 5, version: 2, status: "published" }, { id: 4, version: 1, status: "archived" }] };
const SPEC = { steps: [{ id: "understand", type: "extract", name: "Understand" },
  { id: "limit", type: "rule", name: "Limit", on_fail: "approval", message: "Over", conditions: [{ field: "amount", op: "<=", value: 5000 }] }] };
const DRAFT = { id: 9, key: "x", version: 1, name: "Draft flow", description: "", status: "draft", spec: SPEC, test_cases: [{ name: "small", fields: { amount: 10 }, expect: { outcome: "auto" } }], steps: 2, tests: 1, published_at: null };

test("builder home lists workflows with versions and lets an admin create from a template", async () => {
  const calls = mockFetch({ "GET /auth/me": { user: user("admin"), permissions: ["policies:write", "workflows:operate"] },
    "GET /builder/definitions": { items: [DEF_ROW] }, "GET /builder/templates": [{ key: "expense-approval", name: "Expense approval", description: "d", steps: 4, tests: 3 }],
    "POST /builder/definitions": { id: 77 } });
  navigations.length = 0;
  render(h(AuthProvider, null, h(BuilderHome)));
  await waitFor(() => assert.ok(screen.getByText(/v1 archived/)));
  assert.ok(screen.getByText("published · v2"));
  fireEvent.change(screen.getByPlaceholderText(/Travel expense/), { target: { value: "My flow" } });
  fireEvent.change(screen.getByDisplayValue("Blank workflow"), { target: { value: "expense-approval" } });
  fireEvent.click(screen.getByText("Create draft"));
  await waitFor(() => assert.deepEqual(navigations.at(-1), ["push", "/builder/77"]));
  assert.deepEqual(calls.find((c) => c.key === "POST /builder/definitions").body, { name: "My flow", template_key: "expense-approval" });
});

test("builder home hides creation from non-admins", async () => {
  mockFetch({ "GET /auth/me": { user: user("approver"), permissions: ["workflows:read"] }, "GET /builder/definitions": { items: [DEF_ROW] }, "GET /builder/templates": [] });
  render(h(AuthProvider, null, h(BuilderHome)));
  await waitFor(() => assert.ok(screen.getByText("Expense approval")));
  assert.equal(screen.queryByText("Create draft"), null);
  assert.equal(screen.queryByText("Run"), null); // running needs workflows:operate
});

test("editor saves edits, then blocks publishing while there are unsaved changes", async () => {
  params.id = "9";
  const calls = mockFetch({ "GET /auth/me": { user: user("admin"), permissions: ["policies:write"] }, "GET /builder/definitions/9": DRAFT, "PUT /builder/definitions/9": DRAFT });
  render(h(AuthProvider, null, h(BuilderEditor)));
  const name = await waitFor(() => screen.getByLabelText("Name of step 2"));
  assert.equal(screen.getByText("Save draft").disabled, true); // nothing changed yet
  assert.equal(screen.getByText("Publish").disabled, false);
  fireEvent.change(name, { target: { value: "Spend limit" } });
  await waitFor(() => assert.equal(screen.getByText("Save draft").disabled, false));
  assert.equal(screen.getByText("Publish").disabled, true);
  fireEvent.click(screen.getByText("Save draft"));
  await waitFor(() => assert.ok(screen.getByText("Saved.")));
  const put = calls.find((c) => c.key === "PUT /builder/definitions/9").body;
  assert.equal(put.spec.steps[1].name, "Spend limit");
  assert.equal(put.tests.length, 1);
});

test("editor shows every validation problem when publishing fails", async () => {
  params.id = "9";
  const body = { detail: { message: "1 test case(s) are failing", problems: ["small: expected blocked, got auto"] } };
  mockFetch({ "GET /auth/me": { user: user("admin"), permissions: ["policies:write"] }, "GET /builder/definitions/9": DRAFT, "POST /builder/definitions/9/publish": status(422, body) });
  render(h(AuthProvider, null, h(BuilderEditor)));
  await waitFor(() => screen.getByText("Publish"));
  fireEvent.click(screen.getByText("Publish"));
  await waitFor(() => assert.ok(screen.getByText(/small: expected blocked, got auto/)));
});

test("editor adds, reorders and removes steps and runs a dry test with the current steps", async () => {
  params.id = "9";
  const calls = mockFetch({ "GET /auth/me": { user: user("admin"), permissions: ["policies:write"] }, "GET /builder/definitions/9": DRAFT,
    "POST /builder/test": { outcome: "approval", role: "manager", fields: {}, trace: [{ id: "limit", name: "Limit", type: "rule", result: "flagged", detail: "Over" }] } });
  render(h(AuthProvider, null, h(BuilderEditor)));
  await waitFor(() => screen.getByText("+ Notify"));
  fireEvent.click(screen.getByText("+ Notify"));
  assert.ok(screen.getByLabelText("Name of step 3"));
  fireEvent.click(screen.getByLabelText("Move step 3 up"));
  fireEvent.click(screen.getByLabelText("Remove step 3")); // order was understand, notify, limit
  assert.equal(screen.queryByLabelText("Name of step 3"), null);
  fireEvent.click(screen.getByText("Run test"));
  await waitFor(() => assert.ok(screen.getByText(/Result: Needs approval \(manager\)/)));
  const sent = calls.find((c) => c.key === "POST /builder/test").body;
  assert.deepEqual(sent.spec.steps.map((s) => s.id), ["understand", "notify"]);
});

test("a published version is read-only and offers a new version instead", async () => {
  params.id = "5";
  mockFetch({ "GET /auth/me": { user: user("admin"), permissions: ["policies:write"] }, "GET /builder/definitions/5": { ...DRAFT, id: 5, status: "published", published_at: "2026-01-01T00:00:00Z" } });
  render(h(AuthProvider, null, h(BuilderEditor)));
  await waitFor(() => assert.ok(screen.getByText("Create new version")));
  assert.equal(screen.queryByText("Save draft"), null);
  assert.equal(screen.queryByText("Publish"), null);
});

import LoginPage from "../login/page.jsx";

test("the sign-in page advertises no credentials unless the build opts into demo mode", async () => {
  mockFetch({});
  render(h(LoginPage));
  await waitFor(() => assert.ok(screen.getByText("Sign in", { selector: "h2" })));
  assert.equal(screen.queryByText(/flowforge-demo/), null);
  assert.equal(screen.queryByText("Admin"), null);
  assert.equal(screen.getByLabelText("Email").value, "");
});
