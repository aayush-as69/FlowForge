// Regression test for the open redirect on /login?next=...  Run with `npm test` (node:test, no extra dependencies).
import assert from "node:assert/strict";
import { test } from "node:test";
import { safeNext } from "./safe-redirect.mjs";

test("keeps same-site paths, query strings and hashes", () => {
  assert.equal(safeNext("/dashboard"), "/dashboard");
  assert.equal(safeNext("/workflows/12?tab=audit#top"), "/workflows/12?tab=audit#top");
  assert.equal(safeNext("/functions/procurement"), "/functions/procurement");
});

test("falls back when there is no usable value", () => {
  for (const v of [null, undefined, "", "   ", 42, {}, []]) assert.equal(safeNext(v), "/dashboard", String(v));
  assert.equal(safeNext(null, "/workflows"), "/workflows");
});

test("rejects absolute and protocol-relative URLs", () => {
  for (const v of [
    "//example.com/phish",
    "//example.com",
    "https://example.com/phish",
    "http://example.com",
    "example.com",
    "javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
  ]) {
    assert.equal(safeNext(v), "/dashboard", v);
  }
});

test("rejects tricks browsers normalise into a protocol-relative URL", () => {
  for (const v of [
    "/\\example.com", // backslash is treated as a slash
    "/\\/example.com",
    "\\\\example.com",
    "/\t/example.com", // tabs and newlines are stripped by the URL parser
    "/\n/example.com",
    "/\r/example.com",
    " //example.com",
    "///example.com",
  ]) {
    assert.equal(safeNext(v), "/dashboard", JSON.stringify(v));
  }
});
