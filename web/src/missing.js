// Which finished months each account does not fully cover, by the same rule the server uses to call
// a month complete: one of the account's ranges must hold the whole month. An account is judged from
// the day its data starts, so the days before its first file are not missing; nor is the month in progress.

function lastDay(ym) {
  const [y, m] = ym.split("-").map(Number);
  return `${ym}-${String(new Date(Date.UTC(y, m, 0)).getUTCDate()).padStart(2, "0")}`;
}

function next(ym) {
  const [y, m] = ym.split("-").map(Number);
  return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, "0")}`;
}

function shift(day, by) {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + by)).toISOString().slice(0, 10);
}

// The days from first to last that no range holds, as [start, end] spans. Ranges are sorted and merged.
function gaps(ranges, first, last) {
  const out = [];
  let from = first;
  for (const [start, end] of ranges) {
    if (end < from || start > last) continue;
    if (start > from) out.push([from, shift(start, -1)]);
    from = shift(end, 1);
    if (from > last) break;
  }
  if (from <= last) out.push([from, last]);
  return out;
}

// A statement takes a cycle to close and a few days to be published. Until that long has passed since
// an account's data ends, the days after it are not missing: the file for them does not exist yet.
const NOT_OUT_YET_DAYS = 35;

// The last day the account can be judged on: the end of the last finished month, or the end of its
// own data when its next file is not out yet.
function horizon(ranges, today) {
  const monthEnd = shift(`${today.slice(0, 7)}-01`, -1);
  const dataEnd = ranges[ranges.length - 1][1];
  return dataEnd < monthEnd && shift(dataEnd, NOT_OUT_YET_DAYS) >= today ? dataEnd : monthEnd;
}

// The day an account's data ends, when days after it in a finished month are still to come with its
// next file; otherwise null.
export function waitingAfter(ranges, today) {
  if (!ranges || !ranges.length) return null;
  const until = horizon(ranges, today);
  return until < shift(`${today.slice(0, 7)}-01`, -1) ? until : null;
}

// accounts: [{name, ranges: [[start, end], ...]}]; today: "YYYY-MM-DD".
// Returns [{month: "YYYY-MM", accounts: [{name, whole, gaps: [[start, end], ...]}]}], oldest month
// first, only months with a gap. `whole` says the account has nothing at all for the month.
export function missingMonths(accounts, today) {
  const current = today.slice(0, 7);
  const byMonth = new Map();
  for (const account of accounts) {
    const ranges = account.ranges || [];
    if (!ranges.length) continue;
    const until = horizon(ranges, today);
    for (let ym = ranges[0][0].slice(0, 7); ym < current; ym = next(ym)) {
      const first = `${ym}-01` < ranges[0][0] ? ranges[0][0] : `${ym}-01`;
      const last = lastDay(ym) < until ? lastDay(ym) : until;
      if (first > last) continue;
      if (!ranges.some(([start, end]) => start <= first && end >= last)) {
        const spans = gaps(ranges, first, last);
        const whole = spans.length === 1 && spans[0][0] === `${ym}-01` && spans[0][1] === lastDay(ym);
        byMonth.set(ym, [...(byMonth.get(ym) || []), { name: account.name, whole, gaps: spans }]);
      }
    }
  }
  return [...byMonth.keys()].sort().map((month) => ({ month, accounts: byMonth.get(month) }));
}

// Everything one account lacks, from the day its data starts to the end of the last finished month,
// as [start, end] spans that run across month ends. Ranges are sorted and merged.
export function missingSpans(ranges, today) {
  if (!ranges || !ranges.length) return [];
  const current = today.slice(0, 7);
  const first = ranges[0][0];
  const last = horizon(ranges, today);
  return first > last ? [] : gaps(ranges, first, last);
}

// The whole months a span is made of, or null when it starts or ends inside a month.
export function wholeMonths([start, end]) {
  if (!start.endsWith("-01") || end !== lastDay(end.slice(0, 7))) return null;
  const months = [];
  for (let ym = start.slice(0, 7); ym <= end.slice(0, 7); ym = next(ym)) months.push(ym);
  return months;
}
