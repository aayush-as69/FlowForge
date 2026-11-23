// Test-only ESM loader: resolves the "@/" alias, stubs next/navigation and transpiles JSX with esbuild.
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { transform } from "esbuild";

const SRC = fileURLToPath(new URL("../", import.meta.url));
const EXTS = ["", ".js", ".jsx", ".mjs", "/index.js", "/index.jsx"];

function locate(base) {
  for (const e of EXTS) if (existsSync(base + e) && !base.endsWith("/") && (e || /\.\w+$/.test(base))) return base + e;
  return null;
}

export async function resolve(specifier, context, next) {
  if (specifier === "next/navigation") return { url: new URL("./next-navigation-stub.mjs", import.meta.url).href, shortCircuit: true };
  if (specifier === "next/link") return { url: new URL("./next-link-stub.mjs", import.meta.url).href, shortCircuit: true };
  if (specifier.startsWith("@/")) {
    const file = locate(SRC + specifier.slice(2));
    if (file) return { url: pathToFileURL(file).href, shortCircuit: true };
  }
  if ((specifier.startsWith("./") || specifier.startsWith("../")) && context.parentURL?.startsWith("file:") && !/\.\w+$/.test(specifier)) {
    const file = locate(fileURLToPath(new URL(specifier, context.parentURL)));
    if (file) return { url: pathToFileURL(file).href, shortCircuit: true };
  }
  return next(specifier, context);
}

export async function load(url, context, next) {
  if (url.startsWith("file:") && /\/src\/(?!test\/).*\.(jsx|js)$/.test(url) && !url.includes("node_modules")) {
    const source = await readFile(fileURLToPath(url), "utf8");
    const out = await transform(source, { loader: url.endsWith(".jsx") ? "jsx" : "js", jsx: "automatic", format: "esm", sourcefile: url });
    return { format: "module", source: out.code, shortCircuit: true };
  }
  return next(url, context);
}
