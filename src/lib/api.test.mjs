import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { ApiError, api } from "./api.js";
import { mockFetch, status } from "../test/helpers.mjs";

const realWindow = globalThis.window;
afterEach(() => { globalThis.window = realWindow; });

test("GET returns parsed JSON and sends same-origin, uncached requests", async () => {
  let seen;
  globalThis.fetch = async (url, init) => { seen = { url, init }; return { ok: true, status: 200, json: async () => ({ a: 1 }) }; };
  assert.deepEqual(await api("/dashboard/summary"), { a: 1 });
  assert.equal(seen.url, "/api/dashboard/summary");
  assert.equal(seen.init.credentials, "same-origin");
  assert.equal(seen.init.cache, "no-store");
  assert.equal(seen.init.headers, undefined);
});

test("POST sends a JSON body with a content type", async () => {
  const calls = mockFetch({ "POST /requests": { id: 7 } });
  assert.deepEqual(await api("/requests", { method: "POST", body: { text: "laptop" } }), { id: 7 });
  assert.deepEqual(calls[0].body, { text: "laptop" });
});

test("network failure becomes a friendly ApiError with status 0", async () => {
  globalThis.fetch = async () => { throw new TypeError("fetch failed"); };
  await assert.rejects(api("/x"), (e) => e instanceof ApiError && e.status === 0 && /Cannot reach/.test(e.message));
});

test("server detail and field errors are surfaced", async () => {
  mockFetch({ "POST /requests": status(422, { detail: "Some fields are invalid.", errors: [{ field: "text", message: "too short" }] }) });
  await assert.rejects(api("/requests", { method: "POST", body: {} }), (e) => e.status === 422 && e.message === "Some fields are invalid." && e.errors[0].field === "text");
});

test("5xx without a JSON body uses a retry message, other errors name the status", async () => {
  globalThis.fetch = async () => ({ ok: false, status: 502, json: async () => { throw new Error("not json"); } });
  await assert.rejects(api("/x"), (e) => e.status === 502 && /temporarily unavailable/.test(e.message));
  globalThis.fetch = async () => ({ ok: false, status: 418, json: async () => ({}) });
  await assert.rejects(api("/x"), (e) => e.message === "Request failed (418).");
});

test("401 sends the user to /login with a safe next= unless already there or probing /auth/me", async () => {
  const moves = [];
  const at = (pathname) => { globalThis.window = { location: { pathname, replace: (u) => moves.push(u) } }; };
  mockFetch({ "GET /workflows": status(401, { detail: "Authentication required." }), "GET /auth/me": status(401, { detail: "x" }) });
  at("/workflows/12");
  await assert.rejects(api("/workflows"));
  assert.deepEqual(moves, ["/login?next=%2Fworkflows%2F12"]);
  at("/login");
  await assert.rejects(api("/workflows"));
  at("/dashboard");
  await assert.rejects(api("/auth/me"));
  assert.equal(moves.length, 1);
});

test("structured 422 details keep their message and list of problems", async () => {
  globalThis.fetch = async () => ({ ok: false, status: 422, json: async () => ({ detail: { message: "The workflow is not valid.", problems: ["step 2: bad"] } }) });
  const err = await api("/builder/test", { method: "POST", body: {} }).catch((e) => e);
  assert.equal(err.message, "The workflow is not valid.");
  assert.deepEqual(err.problems, ["step 2: bad"]);
});
