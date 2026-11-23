import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement as h } from "react";
import { renderToStaticMarkup as html } from "react-dom/server";
import { Async, Badge, Button, EmptyState, ErrorState, Field, PageHeader, Pager, StatusBadge, cn } from "./ui.jsx";

test("cn drops falsy classes", () => {
  assert.equal(cn("a", false, null, undefined, "b"), "a b");
});

test("Badge renders its tone and children", () => {
  const out = html(h(Badge, { tone: "green" }, "Verified"));
  assert.match(out, /Verified/);
  assert.match(out, /emerald/);
});

test("StatusBadge falls back to the raw status for unknown values", () => {
  assert.match(html(h(StatusBadge, { status: "something_new" })), /something_new/);
});

test("Button is disabled and marked busy while loading", () => {
  const out = html(h(Button, { loading: true }, "Save"));
  assert.match(out, /disabled/);
  assert.match(out, /Save/);
});

test("PageHeader shows title, subtitle and actions", () => {
  const out = html(h(PageHeader, { title: "Audit trail", subtitle: "What happened", actions: h("span", null, "ACTION") }));
  for (const t of ["Audit trail", "What happened", "ACTION"]) assert.match(out, new RegExp(t));
});

test("ErrorState offers Retry only when it is useful", () => {
  const withRetry = html(h(ErrorState, { error: new Error("boom"), onRetry() {} }));
  assert.match(withRetry, /boom/);
  assert.match(withRetry, /<button[^>]*>Retry<\/button>/);
  assert.doesNotMatch(html(h(ErrorState, { error: new Error("boom") })), /<button/);
  const forbidden = Object.assign(new Error("no"), { status: 403 });
  const out = html(h(ErrorState, { error: forbidden, onRetry() {} }));
  assert.match(out, /does not have access/);
  assert.doesNotMatch(out, /<button/);
});

test("EmptyState renders hint text", () => {
  assert.match(html(h(EmptyState, { title: "Nothing here", hint: "Try another filter" })), /Try another filter/);
});

test("Field shows its error message", () => {
  assert.match(html(h(Field, { label: "Budget", error: "must be positive" }, h("input"))), /must be positive/);
});

test("Pager renders nothing without results and disables the edges", () => {
  const noop = () => {};
  assert.equal(html(h(Pager, { page: 1, pages: 0, total: 0, onPage: noop })), "");
  const single = html(h(Pager, { page: 1, pages: 1, total: 3, onPage: noop }));
  assert.equal((single.match(/disabled=""/g) || []).length, 2);
  const middle = html(h(Pager, { page: 2, pages: 4, total: 80, onPage: noop }));
  assert.match(middle, /80 total/);
  assert.match(middle, /Page 2 of 4/);
  assert.doesNotMatch(middle, /disabled=""/);
});

test("Async renders loading, error, empty and data states", () => {
  const child = (d) => h("p", null, `got ${d.items.length}`);
  const loading = html(h(Async, { state: { data: null, error: null, loading: true } }, child));
  assert.doesNotMatch(loading, /got/);
  assert.match(html(h(Async, { state: { data: null, error: new Error("nope"), loading: false } }, child)), /nope/);
  const empty = Object.assign((d) => !d.items.length, { element: h("i", null, "EMPTY") });
  assert.match(html(h(Async, { state: { data: { items: [] }, error: null, loading: false }, empty }, child)), /EMPTY/);
  assert.match(html(h(Async, { state: { data: { items: [1, 2] }, error: null, loading: false }, empty }, child)), /got 2/);
});
