// The arithmetic behind the overview: figures over several full months, so no single month's
// timing (a pay day that slipped, a yearly bill) decides the headline.

// The latest `n` full months, oldest first. A month still being filled in is left out; if no month
// is full yet, every month is used so there is something to show.
export function recent(months, n) {
  const full = months.filter((m) => m.complete);
  return (full.length ? full : months).slice(-n);
}

// What was kept of everything that came in over the months, and the average month.
export function pooled(months) {
  if (months.length === 0) return null;
  const income = months.reduce((n, m) => n + m.income_cents, 0);
  const spending = months.reduce((n, m) => n + m.spending_cents, 0);
  const each = (cents) => Math.round(cents / months.length);
  return { count: months.length, rate: income > 0 ? (income - spending) / income : null,
    income_cents: each(income), spending_cents: each(spending), saved_cents: each(income - spending) };
}

function averages(months) {
  const sums = {};
  for (const m of months) {
    for (const [name, cents] of Object.entries(m.blocks)) sums[name] = (sums[name] || 0) + cents;
  }
  return Object.fromEntries(Object.entries(sums).map(([name, cents]) => [name, Math.round(cents / months.length)]));
}

// Each spending group's average month over `months`, largest first, beside its average over the
// months `before` (null when there are none), leaving out a group with nothing in either.
export function usualBlocks(months, before) {
  const now = averages(months);
  const then = before.length ? averages(before) : null;
  return Object.entries(now)
    .map(([name, cents]) => ({ name, cents, before_cents: then ? then[name] ?? 0 : null }))
    .filter((b) => b.cents !== 0 || b.before_cents)
    .sort((a, b) => b.cents - a.cents || a.name.localeCompare(b.name));
}

// The latest full month and the one before it (null when there is none). A month still being filled
// in is never the headline.
export function lastTwo(months) {
  const full = months.filter((m) => m.complete);
  return { last: full.at(-1) ?? null, before: full.at(-2) ?? null };
}

// The rate against the target, in whole points: 3, -2 or 0. Null when there is no rate.
export function pointsFromTarget(rate, target) {
  if (rate == null) return null;
  return Math.round(rate * 100) - Math.round(target * 100);
}

// Each spending group in `month`, largest first, with how far it moved from `before` (null when
// there is no month before), leaving out a group with nothing in either.
export function groupMoves(month, before) {
  return Object.entries(month.blocks)
    .map(([name, cents]) => ({ name, cents, moved_cents: before ? cents - (before.blocks[name] ?? 0) : null }))
    .filter((b) => b.cents !== 0 || b.moved_cents)
    .sort((a, b) => b.cents - a.cents || a.name.localeCompare(b.name));
}

// The months with charges that need a look, newest first.
export function needingALook(months) {
  return months
    .map((m) => ({ month: m.month, count: m.uncategorised_count + m.unconfirmed_income_count }))
    .filter((m) => m.count > 0)
    .reverse();
}

// Each spending group in `month` beside its usual figure: its average over the full months given
// (the few before it). `gap_cents` is how far above (positive) or below the month ran; both are
// null when there are no months to compare with. The biggest gaps come first; without a usual
// figure, the biggest amounts. A group with nothing in the month or its usual is left out.
export function againstUsual(month, earlier) {
  const usual = earlier.length ? averages(earlier) : null;
  const names = new Set([...Object.keys(month.blocks), ...Object.keys(usual ?? {})]);
  return [...names]
    .map((name) => {
      const cents = month.blocks[name] ?? 0;
      const usual_cents = usual ? usual[name] ?? 0 : null;
      return { name, cents, usual_cents, gap_cents: usual ? cents - usual_cents : null };
    })
    .filter((g) => g.cents !== 0 || g.usual_cents)
    .sort((a, b) => Math.abs(b.gap_cents ?? 0) - Math.abs(a.gap_cents ?? 0) || b.cents - a.cents || a.name.localeCompare(b.name));
}
