/** Formatting helpers for the analytics page (kept out of the page file so they can be unit tested). */
export function money(value, currency = "INR") {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

export function hoursLabel(h) {
  if (h === null || h === undefined) return "—";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${h.toFixed(1)} h`;
  return `${(h / 24).toFixed(1)} d`;
}

/** Bar heights as percentages of the largest value, never below a visible sliver for non-zero values. */
export function barHeights(values) {
  const max = Math.max(0, ...values);
  return values.map((v) => (max === 0 ? 0 : v === 0 ? 0 : Math.max(Math.round((v / max) * 100), 4)));
}
