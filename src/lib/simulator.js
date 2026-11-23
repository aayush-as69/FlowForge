/** Helpers for the policy simulator page. */

/** Numeric top-level params that can be edited with a number box (lists and weight maps are left to the real editor). */
export function editableFields(policy) {
  return Object.entries(policy.params || {}).filter(([, v]) => typeof v === "number").map(([k]) => k);
}

/** Only policies whose draft differs from the stored value become changes, with the full params object merged. */
export function buildChanges(policies, draft) {
  const changes = [];
  for (const p of policies) {
    const edits = draft[p.id];
    if (!edits) continue;
    const params = { ...p.params };
    let differs = false;
    for (const [key, raw] of Object.entries(edits)) {
      const n = Number(raw);
      if (raw === "" || Number.isNaN(n)) continue;
      if (n !== p.params[key]) differs = true;
      params[key] = n;
    }
    if (differs) changes.push({ policy_id: p.id, params });
  }
  return changes;
}

export const OUTCOME_LABELS = {
  auto: "Runs automatically", review: "Checked by a person", human: "Person decides", blocked: "Blocked by policy", exception: "Price exception",
};

/** Signed change for display, e.g. "−12", "+3", "0". */
export function delta(before, after) {
  const d = after - before;
  return d === 0 ? "0" : d > 0 ? `+${d}` : `−${Math.abs(d)}`;
}
