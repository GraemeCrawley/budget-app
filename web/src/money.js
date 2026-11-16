// Money arrives as integer cents; these turn it into words. No Date parsing, so no time-zone drift.
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
  "September", "October", "November", "December"];

function grouped(n) {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Whole dollars, halves rounded away from zero: dollars(-450) is "-$5".
export function dollars(cents) {
  const whole = Math.floor((Math.abs(cents) + 50) / 100);
  return `${cents < 0 && whole > 0 ? "-" : ""}$${grouped(whole)}`;
}

export function exact(cents) {
  const abs = Math.abs(cents);
  const rest = String(abs % 100).padStart(2, "0");
  return `${cents < 0 ? "-" : ""}$${grouped(Math.floor(abs / 100))}.${rest}`;
}

export function percent(rate) {
  if (rate === null || rate === undefined) return "–";
  return `${Math.round(rate * 100)}%`;
}

// "2026-01" -> "January 2026"
export function monthName(ym) {
  return `${monthOnly(ym)} ${ym.slice(0, 4)}`;
}

// "2026-01" -> "January"
export function monthOnly(ym) {
  return MONTHS[Number(ym.slice(5, 7)) - 1];
}

// "2026-01" -> "Jan"
export function shortMonth(ym) {
  return monthOnly(ym).slice(0, 3);
}

// "2026-01-05" -> "Jan 5"
export function shortDate(iso) {
  return `${shortMonth(iso)} ${Number(iso.slice(8, 10))}`;
}

// "2026-07-18" -> "Jul 18, 2026"
export function longDate(iso) {
  return `${shortDate(iso)}, ${iso.slice(0, 4)}`;
}
