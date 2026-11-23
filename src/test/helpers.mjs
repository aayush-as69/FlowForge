// Tiny fetch mock: routes is { "GET /path": body | (init) => body | Response-like }.
export function mockFetch(routes) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const method = init.method || "GET";
    const key = `${method} ${String(url).replace(/^\/api/, "")}`;
    calls.push({ key, body: init.body ? JSON.parse(init.body) : undefined });
    const hit = routes[key] ?? Object.entries(routes).find(([k]) => key.startsWith(k.replace(/\*$/, "")) && k.endsWith("*"))?.[1];
    if (hit === undefined) return { ok: false, status: 404, json: async () => ({ detail: `no mock for ${key}` }) };
    const value = typeof hit === "function" ? hit(init) : hit;
    if (value && value.__status) return { ok: value.__status < 400, status: value.__status, json: async () => value.body };
    return { ok: true, status: 200, json: async () => value };
  };
  return calls;
}
export const status = (code, body) => ({ __status: code, body });
