// Income and spending by month, as two lines in dollars. The gap between them is what was saved.
// Each other month is a link to that month, as in RateChart.
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { dollars, monthName, shortMonth } from "../money.js";
import { Reading, useScrub } from "./Scrub.jsx";

const STEPS = [500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000, 100000];
const MAX_STEPS = 4;
const MAX_LABELS = 6;
const AXIS = 48; // the money axis's width
const RIGHT = 16; // the chart's right margin
const LINES = [
  { key: "income", name: "Income", colour: "var(--accent)" },
  { key: "spending", name: "Spending", colour: "var(--warn)" },
];

// Amounts are in cents. Returns a dollar axis that holds zero, ends on round numbers and has few ticks.
export function moneyScale(cents) {
  const values = cents.map((c) => c / 100);
  const top = Math.max(0, ...values);
  const bottom = Math.min(0, ...values);
  const step = STEPS.find((s) => (top - bottom) / s <= MAX_STEPS) ?? STEPS[STEPS.length - 1];
  const low = Math.floor(bottom / step) * step || 0;
  const high = Math.max(step, Math.ceil(top / step) * step);
  const ticks = [];
  for (let t = low; t <= high; t += step) ticks.push(t);
  return { domain: [low, high], ticks };
}

// 2000 -> "$2k", 500 -> "$500"
export function shortDollars(v) {
  const abs = Math.abs(v);
  return `${v < 0 ? "-" : ""}$${abs >= 1000 ? `${abs / 1000}k` : abs}`;
}

function labelledMonths(data) {
  if (data.length <= 8) return data.map((d) => d.month);
  const step = Math.ceil(data.length / MAX_LABELS);
  const picked = [];
  for (let i = data.length - 1; i >= 0; i -= step) picked.unshift(data[i].month);
  return picked;
}

function Dot({ cx, cy, payload, chosen, colour }) {
  if (cx == null || cy == null) return null;
  const big = payload.month === chosen;
  return <circle cx={cx} cy={cy} r={big ? 5 : 3} fill={colour} stroke="var(--surface)" strokeWidth={big ? 2 : 0} />;
}

export default function MoneyChart({ months, chosen, links = true }) {
  const data = months.map((m) => ({ month: m.month, income: m.income_cents / 100, spending: m.spending_cents / 100 }));
  const { domain, ticks } = moneyScale(months.flatMap((m) => [m.income_cents, m.spending_cents]));
  const scrub = useScrub(months.length);
  const read = scrub.at == null ? null : months[scrub.at];
  // the key above the chart names one month: the one under the finger, else the chosen or latest
  const listed = read ?? months.find((m) => m.month === chosen) ?? months.at(-1);
  return (
    <>
      {listed && <p className="keyhead" role="status"><span>{monthName(listed.month)}</span></p>}
      <p className="legend small muted">
        {LINES.map((l) => (
          <span key={l.key}>
            <i style={{ background: l.colour }} />{l.name}
            {listed && <strong className="num">{dollars(listed[`${l.key}_cents`])}</strong>}
          </span>
        ))}
      </p>
      <div className="chartwrap" ref={scrub.wrap} {...scrub.handlers}>
        <div className="chart short" role="img" aria-label="Income and spending by month">
          <ResponsiveContainer width="100%" height={140} initialDimension={{ width: 320, height: 140 }}>
            <LineChart data={data} accessibilityLayer={false} margin={{ top: 8, right: RIGHT, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              {domain[0] < 0 && <ReferenceLine y={0} stroke="var(--muted)" strokeOpacity={0.6} />}
              <XAxis dataKey="month" ticks={labelledMonths(data)} interval={0} tickLine={false} axisLine={false}
                tickFormatter={shortMonth} tick={{ fill: "var(--muted)", fontSize: 11 }} />
              <YAxis domain={domain} ticks={ticks} width={AXIS} tickLine={false} axisLine={false}
                tickFormatter={shortDollars} tick={{ fill: "var(--muted)", fontSize: 11 }} />
              {LINES.map((l) => (
                <Line key={l.key} type="linear" dataKey={l.key} stroke={l.colour} strokeWidth={2.5}
                  isAnimationActive={false} activeDot={false}
                  dot={(props) => <Dot key={props.payload.month} {...props} chosen={chosen} colour={l.colour} />} />
              ))}
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
        <Reading scrub={scrub} count={months.length} left={AXIS} right={RIGHT} />
      </div>
    </>
  );
}
