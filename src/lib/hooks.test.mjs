import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { cleanup, renderHook, waitFor, act } from "@testing-library/react";
import { useApi } from "./hooks.js";
import { mockFetch, status } from "../test/helpers.mjs";

afterEach(cleanup);

test("useApi starts loading, then exposes the data", async () => {
  const calls = mockFetch({ "GET /things": { n: 1 } });
  const { result } = renderHook(() => useApi("/things"));
  assert.equal(result.current.loading, true);
  await waitFor(() => assert.equal(result.current.loading, false));
  assert.deepEqual(result.current.data, { n: 1 });
  assert.equal(result.current.error, null);
  assert.equal(calls.length, 1);
});

test("useApi reports errors and keeps stale data on a failed reload", async () => {
  let fail = false;
  mockFetch({ "GET /things": () => (fail ? status(500, { detail: "db down" }) : { n: 1 }) });
  const { result } = renderHook(() => useApi("/things"));
  await waitFor(() => assert.deepEqual(result.current.data, { n: 1 }));
  fail = true;
  await act(async () => { await result.current.reload(); });
  assert.equal(result.current.error.message, "db down");
  assert.deepEqual(result.current.data, { n: 1 });
  assert.equal(result.current.loading, false);
});

test("useApi with no path never calls the API and is not loading", async () => {
  const calls = mockFetch({});
  const { result } = renderHook(() => useApi(null));
  assert.equal(result.current.loading, false);
  assert.equal(result.current.data, null);
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(calls.length, 0);
});

test("useApi refetches when the path changes and shows loading until the new answer", async () => {
  mockFetch({ "GET /a": { id: "a" }, "GET /b": { id: "b" } });
  const { result, rerender } = renderHook(({ p }) => useApi(p), { initialProps: { p: "/a" } });
  await waitFor(() => assert.equal(result.current.data?.id, "a"));
  rerender({ p: "/b" });
  assert.equal(result.current.loading, true);
  await waitFor(() => assert.equal(result.current.data?.id, "b"));
  assert.equal(result.current.loading, false);
});

test("useApi polls on an interval and stops after unmount", async () => {
  let n = 0;
  mockFetch({ "GET /tick": () => ({ n: ++n }) });
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  const { result, unmount } = renderHook(() => useApi("/tick", { interval: 15 }));
  await waitFor(() => assert.ok(result.current.data?.n >= 2));
  unmount();
  const seen = n;
  await new Promise((r) => setTimeout(r, 60));
  assert.equal(n, seen);
});
