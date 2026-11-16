// Each spending group keeps one colour everywhere it appears: Home's tiles and the stacked chart.
export const BLOCK_ORDER = ["Bills", "Food", "Everything else", "Big purchases", "Subscriptions", "Buckets"];
export const BLOCK_COLOUR = {
  Bills: "#ff8a5c", Food: "#ffd84d", "Everything else": "#8fd3ff", "Big purchases": "#f3b8ff",
  Subscriptions: "#9af0c4", Buckets: "#b9b4e8",
};
export const colourOf = (name) => BLOCK_COLOUR[name] || "var(--muted)";

// The groups that appear in any of these months, in the fixed order, unknown ones last.
export function groupsIn(months) {
  const seen = new Set(months.flatMap((m) => Object.entries(m.blocks).filter(([, c]) => c > 0).map(([n]) => n)));
  return [...BLOCK_ORDER.filter((n) => seen.has(n)), ...[...seen].filter((n) => !BLOCK_ORDER.includes(n)).sort()];
}
