// A month's spending as it built up day by day, split by group. Works from the month's charges as
// the server lists them: a charge counts when it has a group, and money out is a negative amount.
import { BLOCK_ORDER } from "./blockColours.js";

const pad = (n) => String(n).padStart(2, "0");

export function daysIn(ym) {
  return new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(5, 7), 0)).getUTCDate();
}

// One row per day: {day, date, total, <group>: cents so far}. `through` (a date) ends the rows
// early for a month still under way. A refund lowers its group's running figure, never below zero.
export function dailyByGroup(transactions, ym, through = null) {
  const spent = transactions.filter((t) => t.block && t.date.slice(0, 7) === ym);
  const seen = new Set(spent.map((t) => t.block));
  const groups = [...BLOCK_ORDER.filter((g) => seen.has(g)), ...[...seen].filter((g) => !BLOCK_ORDER.includes(g)).sort()];
  const last = through && through.slice(0, 7) === ym ? +through.slice(8, 10) : daysIn(ym);
  const running = Object.fromEntries(groups.map((g) => [g, 0]));
  const days = [];
  for (let day = 1; day <= last; day += 1) {
    const date = `${ym}-${pad(day)}`;
    for (const t of spent) if (t.date === date) running[t.block] -= t.amount_cents;
    const row = { day, date, total: 0 };
    for (const g of groups) {
      row[g] = Math.max(0, running[g]);
      row.total += row[g];
    }
    days.push(row);
  }
  return { groups, days };
}
