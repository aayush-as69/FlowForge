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
