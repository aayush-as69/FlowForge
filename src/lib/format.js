export const inr = (n) => (n === null || n === undefined ? "—" : `₹${Math.round(n).toLocaleString("en-IN")}`);

const toDate = (v) => (v ? new Date(v) : null);

export function fmtTime(v) {
  const d = toDate(v);
  return d ? d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) : "—";
}

export function fmtDateTime(v) {
  const d = toDate(v);
  return d ? d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }) : "—";
}

export function fmtDate(v) {
  if (!v) return "—";
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v);
  return d.toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
}

export function relTime(v) {
  const d = toDate(v);
  if (!d) return "—";
  const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export function duration(ms) {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.round(ms / 60000)} min`;
}

export const titleCase = (s) => (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
