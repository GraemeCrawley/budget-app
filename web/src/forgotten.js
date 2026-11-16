// Charges too old to remember. They are still money that left, so they stay in spending, filed
// under one honest name instead of a guess. No rule is made for the shop: the next charge from it
// is asked about afresh.
export const FORGOTTEN = "Can't remember";
export const OLD_DAYS = 90;
export const SMALL_CENTS = 20000; // anything this big is worth a moment's thought

// The charges in the unplaced groups that are older than OLD_DAYS and under SMALL_CENTS.
export function oldAndSmall(unplaced, today = new Date()) {
  const cutoff = new Date(today.getTime() - OLD_DAYS * 86400000).toISOString().slice(0, 10);
  return unplaced.flatMap((g) => g.charges).filter((c) => c.date < cutoff && Math.abs(c.amount_cents) < SMALL_CENTS);
}
