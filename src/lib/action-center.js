export function ageLabel(hours) {
  if (hours < 1) return "under 1h";
  if (hours < 48) return `${Math.round(hours)}h`;
  return `${Math.round(hours / 24)}d`;
}

export function filterItems(items, tab) {
  if (tab === "mine") return items.filter((i) => i.mine);
  if (tab === "overdue") return items.filter((i) => i.overdue);
  if (tab === "all") return items;
  return items.filter((i) => ({ approvals: "approval", exceptions: "exception", failed: "failed_workflow" })[tab] === i.type);
}
