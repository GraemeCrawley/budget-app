// A thin bar scaled against `max`. Decorative: the amount beside it carries the meaning.
export default function Bar({ value, max }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <span className="bar" aria-hidden="true">
      <i style={{ width: `${pct}%` }} />
    </span>
  );
}
