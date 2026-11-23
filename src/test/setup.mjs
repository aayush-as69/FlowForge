// Loaded with `node --import`: registers the loader and provides a browser-like environment.
import { register } from "node:module";
import { JSDOM } from "jsdom";

register("./loader.mjs", import.meta.url);

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const key of ["window", "document", "navigator", "HTMLElement", "Node", "Event", "MouseEvent", "KeyboardEvent", "getComputedStyle", "MutationObserver"]) {
  Object.defineProperty(globalThis, key, { value: dom.window[key] ?? dom.window, configurable: true, writable: true });
}
globalThis.window = dom.window;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Test files run in parallel processes; give async queries more headroom than the 1s default so slow starts don't flake.
const { configure } = await import("@testing-library/dom");
configure({ asyncUtilTimeout: 5000 });
