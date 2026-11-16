// The savings rate by month. The chosen month's dot is drawn larger. No target line yet (Plan 3).
// Each other month is a link to that month: an invisible column centred on its dot.
// The axis never leaves -100% to 100%: a month beyond that is drawn at the edge with a hollow marker.
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { monthName, monthOnly, percent, shortMonth } from "../money.js";
import { Reading, useScrub } from "./Scrub.jsx";

const LIMIT = 100;
const STEP = 25;
const FIXED_TICKS = [-100, -50, 0, 50, 100];
const MAX_LABELS = 6;
const AXIS = 48; // the rate axis's width
const RIGHT = 16; // the chart's right margin

// Rates are in percent. Returns the axis domain (clamped to +-100, rounded outward to a multiple of
// 25, always holding 0), a short set of ticks inside it, and which rates fell outside the range.
export function chartScale(rates) {
  const known = rates.filter((r) => r != null);
  const clampedRates = known.map((r) => Math.max(-LIMIT, Math.min(LIMIT, r)));
  const low = Math.floor(Math.min(0, ...clampedRates) / STEP) * STEP || 0;
  let high = Math.ceil(Math.max(0, ...clampedRates) / STEP) * STEP;
  if (high === low) high = STEP;
  const ticks = [...new Set([low, high, ...FIXED_TICKS.filter((t) => t >= low && t <= high)])]
    .sort((a, b) => a - b);
  return { domain: [low, high], ticks, clamped: rates.map((r) => r != null && Math.abs(r) > LIMIT) };
}

// At most MAX_LABELS month labels when there are many months, evenly spaced and ending on the last.
function labelledMonths(data) {
  if (data.length <= 8) return data.map((d) => d.month);
  const step = Math.ceil(data.length / MAX_LABELS);
  const picked = [];
  for (let i = data.length - 1; i >= 0; i -= step) picked.unshift(data[i].month);
  return picked;
}

function Dot({ cx, cy, payload, chosen }) {
  if (cx == null || cy == null || payload.rate == null) return null;
  const big = payload.month === chosen;
  if (payload.clamped) {
    return <circle cx={cx} cy={cy} r={big ? 5 : 4} fill="var(--surface)" stroke="var(--accent)" strokeWidth={2} />;
  }
  return <circle cx={cx} cy={cy} r={big ? 5 : 3} fill="var(--accent)" stroke="var(--surface)" strokeWidth={big ? 2 : 0} />;
}

export default function RateChart({ months, chosen, links = true }) {
  const actual = months.map((m) => (m.savings_rate == null ? null : Math.round(m.savings_rate * 1000) / 10));
  const { domain, ticks, clamped } = chartScale(actual);
  const data = months.map((m, i) => ({
    month: m.month,
    rate: actual[i] == null ? null : Math.max(-LIMIT, Math.min(LIMIT, actual[i])),
    clamped: clamped[i],
  }));
  const off = months.map((m, i) => ({ m, rate: actual[i] })).filter((_, i) => clamped[i]);
  const scrub = useScrub(months.length);
  const read = scrub.at == null ? null : months[scrub.at];
  return (
    <>
      <div className="chartwrap" ref={scrub.wrap} {...scrub.handlers}>
      <div className="chart" role="img" aria-label="Savings rate by month">
        <ResponsiveContainer width="100%" height={160} initialDimension={{ width: 320, height: 160 }}>
          <LineChart data={data} accessibilityLayer={false} margin={{ top: 8, right: RIGHT, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <ReferenceLine y={0} stroke="var(--muted)" strokeOpacity={0.6} />
            <XAxis dataKey="month" ticks={labelledMonths(data)} interval={0} tickLine={false} axisLine={false}
              tickFormatter={shortMonth} tick={{ fill: "var(--muted)", fontSize: 11 }} />
            <YAxis domain={domain} ticks={ticks} width={AXIS} tickLine={false} axisLine={false}
              tickFormatter={(v) => `${v}%`} tick={{ fill: "var(--muted)", fontSize: 11 }} />
            <Line type="linear" dataKey="rate" stroke="var(--accent)" strokeWidth={2.5} isAnimationActive={false}
              dot={(props) => <Dot key={props.payload.month} {...props} chosen={chosen} />} activeDot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
        {links && months.length > 1 && (
          <div className="chartlinks" style={{ left: AXIS, right: RIGHT }}>
            {months.map((m, i) => m.month !== chosen && (
              <a key={m.month} href={`#/month/${m.month}`} aria-label={monthName(m.month)}
                style={{ position: "absolute", top: 0, bottom: 0, width: `${100 / (months.length - 1)}%`,
                  left: `${((i - 0.5) / (months.length - 1)) * 100}%` }} />
            ))}
          </div>
        )}
        <Reading scrub={scrub} count={months.length} left={AXIS} right={RIGHT}>
          {read && <>{monthName(read.month)} <strong className="num">{read.savings_rate == null ? "no income" : percent(read.savings_rate)}</strong></>}
        </Reading>
      </div>
      {off.length === 1 && (
        <p className="small muted">{monthOnly(off[0].m.month)} is off the chart ({percent(off[0].rate / 100)}).</p>
      )}
      {off.length > 1 && <p className="small muted">{off.length} months are off the chart.</p>}
    </>
  );
}
