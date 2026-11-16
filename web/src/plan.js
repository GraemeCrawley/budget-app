// Budgets: what each category was given, by the month or by the year, against what was spent.
const USUAL_MONTHS = 3;

// One month's spending by category, whichever group each charge fell in.
export function spentByCategory(m) {
  const out = {};
  for (const within of Object.values(m?.categories ?? {})) {
    for (const [name, cents] of Object.entries(within)) out[name] = (out[name] ?? 0) + cents;
  }
  return out;
}

// Each category's average over the last three full months, for the hint beside a budget.
export function usualByCategory(months) {
  const full = months.filter((m) => m.complete).slice(-USUAL_MONTHS);
  const out = {};
  for (const m of full) {
    for (const [name, cents] of Object.entries(spentByCategory(m))) out[name] = (out[name] ?? 0) + cents;
  }
  for (const name of Object.keys(out)) out[name] = Math.round(out[name] / full.length);
  return out;
}

// Each budget against the month (a monthly one) or against the year so far up to and including
// that month (a yearly one). Furthest over first, then the fullest.
export function budgetRows(budgets, months, ym) {
  const m = months.find((x) => x.month === ym);
  const month = spentByCategory(m);
  const soFar = {};
  for (const x of months) {
    if (x.month.slice(0, 4) !== ym.slice(0, 4) || x.month > ym) continue;
    for (const [name, cents] of Object.entries(spentByCategory(x))) soFar[name] = (soFar[name] ?? 0) + cents;
  }
  return budgets.map((b) => {
    const spent = (b.period === "year" ? soFar : month)[b.category] ?? 0;
    return { category: b.category, period: b.period, budget_cents: b.cents, spent_cents: spent, left_cents: b.cents - spent };
  }).sort((a, b) => a.left_cents / a.budget_cents - b.left_cents / b.budget_cents || a.category.localeCompare(b.category));
}
