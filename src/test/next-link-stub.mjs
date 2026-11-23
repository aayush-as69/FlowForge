import { createElement } from "react";

// next/link outside a Next.js app: a plain anchor is enough to assert on destinations.
export default function Link({ href, children, prefetch, ...rest }) {
  return createElement("a", { href: typeof href === "string" ? href : href?.pathname, ...rest }, children);
}
