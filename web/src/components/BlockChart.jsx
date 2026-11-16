// A block's spending by month as bars: at most a year of them, the chosen month in the accent
// colour. No amounts are written on the bars (the chosen month's is the screen's heading, and a
// label beside a taller neighbour collides with it). Press or drag to read any month; a tap on
// another month's column opens the same block in that month.
import { Bar, BarChart, Cell, ResponsiveContainer, XAxis } from "recharts";
import { dollars, monthName, shortMonth } from "../money.js";
import { Reading, useScrub } from "./Scrub.jsx";

const SIDE = 8; // the chart's left and right margin, which the row of links must match
const SHOWN = 12;
const MAX_LABELS = 6;

// Up to SHOWN months in a row that hold the chosen one: the latest ones, unless the chosen month is
// older, in which case it sits with three months after it.
export function windowOf(months, chosen) {
  if (months.length <= SHOWN) return months;
  const at = months.findIndex((m) => m.month === chosen);
  const end = at < 0 ? months.length : Math.min(months.length, Math.max(at + 4, SHOWN));
  return months.slice(end - SHOWN, end);
}

export const SPLIT = [
  { name: "Eating out", key: "out", colour: "#ff8a5c", of: (m) => m.food_out_cents ?? 0 },
  { name: "Eating at home", key: "home", colour: "#9af0c4", of: (m) => m.food_home_cents ?? 0 },
];

// category: one category of the block instead of the whole block. split: the whole of Food drawn
// as eating out stacked on eating at home.
export default function BlockChart({ months, block, chosen, category = null, split = false }) {
  const shown = windowOf(months, chosen);
  const every = Math.ceil(shown.length / MAX_LABELS);
  const what = category ?? block;
  const centsOf = (m) => (category ? m.categories?.[block]?.[category] ?? 0 : m.blocks[block] ?? 0);
  const data = shown.map((m, i) => ({
    month: m.month, cents: centsOf(m), out: SPLIT[0].of(m), home: SPLIT[1].of(m),
    // month names thin out when there are many, counted back from the newest so it is always named
    label: (shown.length - 1 - i) % every === 0 ? shortMonth(m.month) : "",
  }));
  const scrub = useScrub(shown.length, true);
  const read = scrub.at == null ? null : data[scrub.at];
  const bars = split
    ? SPLIT.map((s, i) => ({ key: s.key, fill: () => s.colour, top: i === SPLIT.length - 1 })).reverse()
    : [{ key: "cents", fill: (d) => (d.month === chosen ? "var(--accent)" : "var(--muted)"), top: true }];
  const faded = (d) => (d.month === chosen ? 1 : split ? 0.45 : 0.4);
  return (
    <div className="chartwrap" ref={scrub.wrap} {...scrub.handlers}>
      <div className="chart short" role="img" aria-label={`${what} by month`}>
        <ResponsiveContainer width="100%" height={140} initialDimension={{ width: 320, height: 140 }}>
          <BarChart data={data} accessibilityLayer={false} margin={{ top: 8, right: SIDE, bottom: 0, left: SIDE }}>
            <XAxis dataKey="month" tickLine={false} axisLine={false} interval={0}
              tickFormatter={(_, i) => data[i]?.label ?? ""} tick={{ fill: "var(--muted)", fontSize: 11 }} />
            {bars.map((b) => (
              <Bar key={b.key} dataKey={b.key} stackId="a" radius={b.top ? [4, 4, 0, 0] : 0} isAnimationActive={false}>
                {data.map((d) => <Cell key={d.month} fill={b.fill(d)} fillOpacity={faded(d)} />)}
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="chartlinks" style={{ left: SIDE, right: SIDE }}>
        {shown.map((m) => (m.month !== chosen && block in m.blocks
          ? <a key={m.month} href={`#/block/${m.month}/${encodeURIComponent(block)}`}
              aria-label={`${block} in ${monthName(m.month)}`} />
          : <span key={m.month} />))}
      </div>
      <Reading scrub={scrub} count={shown.length} left={SIDE} right={SIDE} bands>
        {read && (split
          ? <>{monthName(read.month)} out <strong className="num">{dollars(read.out)}</strong> home <strong className="num">{dollars(read.home)}</strong></>
          : <>{monthName(read.month)} <strong className="num">{dollars(read.cents)}</strong></>)}
      </Reading>
    </div>
  );
}
