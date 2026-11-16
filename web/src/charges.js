// A month's charges, asked for once however many parts of a screen want them at the same moment.
import { get } from "./api.js";

const asking = new Map();

export function monthCharges(ym) {
  if (!asking.has(ym)) {
    const request = get(`transactions?month=${ym}`).finally(() => asking.delete(ym));
    asking.set(ym, request);
  }
  return asking.get(ym);
}

// The month's largest single amounts of money out, biggest first.
export function biggest(transactions, n) {
  return transactions.filter((t) => t.block && t.amount_cents < 0)
    .sort((a, b) => a.amount_cents - b.amount_cents || b.id - a.id).slice(0, n);
}
