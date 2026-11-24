export class ApiError extends Error {
  constructor(message, status = 0, errors = null, problems = null) {
    super(message);
    this.status = status;
    this.errors = errors;
    this.problems = problems; // list of human-readable problems (e.g. workflow validation), when the API gives one
  }
}

export async function api(path, { method = "GET", body } = {}) {
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Cannot reach the FlowForge API. It may still be starting — check your connection and retry.", 0);
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login") && path !== "/auth/me") {
      window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
    const fallback =
      res.status >= 500 || res.status === 502 || res.status === 503
        ? "The FlowForge API is temporarily unavailable. Please retry in a few seconds."
        : `Request failed (${res.status}).`;
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail : typeof detail?.message === "string" ? detail.message : fallback;
    throw new ApiError(message, res.status, data?.errors || null, Array.isArray(detail?.problems) ? detail.problems : null);
  }
  return data;
}
