// One month's spending as it built up day by day, stacked by group, with the month before as a
// dashed line to compare against. The key sits above the chart: the day being read, the
// running total, and each group so far. Press or drag to read another day. Loads its own charges, so the month page can show
// its figures without waiting for it.
import { Area, ComposedChart, Line, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { colourOf } from "../blockColours.js";
import { monthCharges } from "../charges.js";
import { dailyByGroup } from "../daily.js";
import { dollars, monthOnly, shortDate } from "../money.js";
import useLoad from "../useLoad.js";
import { shortDollars } from "./MoneyChart.jsx";
import { Reading, useScrub } from "./Scrub.jsx";

const AXIS = 44;
const RIGHT = 8;
const TICKS = [1, 8, 15, 22, 29];

export default function DailyChart({ ym, before, through }) {
  const { data } = useLoad(() => Promise.all([
    monthCharges(ym),
    before ? monthCharges(before) : Promise.resolve({ transactions: [] }),
  ]), [ym, before]);
  const now = data ? dailyByGroup(data[0].transactions, ym, through) : { groups: [], days: [] };
  const then = data && before ? dailyByGroup(data[1].transactions, before).days : [];
  const scrub = useScrub(now.days.length);
  if (!data || now.groups.length === 0) return null;

  const { groups, days } = now;
  const rows = days.map((d, i) => ({
    day: d.day, before: then[i] ? then[i].total / 100 : null,
    ...Object.fromEntries(groups.map((g) => [g, d[g] / 100])),
  }));
  const read = scrub.at == null ? null : days[scrub.at];
  const listed = read ?? days.at(-1);
  // a 31-day month read on its last day is set against the whole of a shorter month before
  const earlier = then[Math.min(listed.day, then.length) - 1];
  return (
    <section className="panel">
      <div className="row"><h2>Day by day</h2><span className="small muted">spending so far, by group</span></div>
      <p className="keyhead" role="status">
        <span>By {shortDate(listed.date)}</span><strong className="num">{dollars(listed.total)}</strong>
      </p>
      <ul className="stackkey small" aria-label={`Spent by ${shortDate(listed.date)}`}>
        {groups.map((g) => (
          <li key={g}><i style={{ background: colourOf(g) }} /><span>{g}</span><span className="num muted">{dollars(listed[g])}</span></li>
        ))}
        {before && earlier && (
          <li className="wide"><i className="dash" /><span>{monthOnly(before)} by then</span><span className="num muted">{dollars(earlier.total)}</span></li>
        )}
      </ul>
      <div className="chartwrap" ref={scrub.wrap} {...scrub.handlers}>
        <div className="chart" role="img" aria-label="Spending so far by day and group">
          <ResponsiveContainer width="100%" height={160} initialDimension={{ width: 320, height: 160 }}>
            <ComposedChart data={rows} accessibilityLayer={false} margin={{ top: 8, right: RIGHT, bottom: 0, left: 0 }}>
              <XAxis dataKey="day" type="number" domain={[1, days.length]} ticks={TICKS.filter((d) => d <= days.length)}
                tickLine={false} axisLine={false} tick={{ fill: "var(--muted)", fontSize: 11 }} />
              <YAxis width={AXIS} tickLine={false} axisLine={false} tickCount={4} tickFormatter={shortDollars}
                tick={{ fill: "var(--muted)", fontSize: 11 }} />
              {groups.map((g) => (
                <Area key={g} dataKey={g} stackId="spent" type="stepAfter" stroke="none" fill={colourOf(g)}
                  fillOpacity={0.9} isAnimationActive={false} activeDot={false} />
              ))}
              {before && (
                <Line dataKey="before" type="stepAfter" stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="4 3"
                  dot={false} activeDot={false} isAnimationActive={false} connectNulls={false} />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <Reading scrub={scrub} count={days.length} left={AXIS} right={RIGHT} />
      </div>
    </section>
  );
}
