export class ApiError extends Error {
  constructor(message, status = 0, errors = null) {
    super(message);
    this.status = status;
    this.errors = errors;
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
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    }
    const fallback =
      res.status >= 500 || res.status === 502 || res.status === 503
        ? "The FlowForge API is temporarily unavailable. Please retry in a few seconds."
        : `Request failed (${res.status}).`;
    throw new ApiError(typeof data?.detail === "string" ? data.detail : fallback, res.status, data?.errors || null);
  }
  return data;
}
