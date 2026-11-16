// One group's month drawn against its usual, on a scale shared by every group in the list. The
// solid part is what was spent up to the usual figure; spending past it continues in the warning
// colour, and falling short leaves a pale stretch up to the tick that marks the usual.
// Decorative: the words beside it say the same thing.
export default function UsualBar({ cents, usual, max }) {
  const pct = (v) => (max > 0 ? Math.max(0, Math.min(100, (v / max) * 100)) : 0);
  const base = pct(Math.min(cents, usual));
  const over = cents > usual;
  return (
    <span className="usualbar" aria-hidden="true">
      <i className="spent" style={{ width: `${base}%` }} />
      <i className={over ? "over" : "under"} style={{ left: `${base}%`, width: `${Math.abs(pct(cents) - pct(usual))}%` }} />
      <i className="tick" style={{ left: `${pct(usual)}%` }} />
    </span>
  );
}
