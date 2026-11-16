// Spending by month as stacked bars, one colour per group, so both the total and what it was made
// of can be compared across months. At most a year; the chosen month stands at full strength.
// The key sits above the chart: the month being read, its total, and each group's amount. Press or
// drag to read another month.
import { Bar, BarChart, Cell, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { colourOf, groupsIn } from "../blockColours.js";
import { dollars, monthName, shortMonth } from "../money.js";
import { windowOf } from "./BlockChart.jsx";
import { shortDollars } from "./MoneyChart.jsx";
import { Reading, useScrub } from "./Scrub.jsx";

const AXIS = 44;
const RIGHT = 8;
const MAX_LABELS = 6;

export default function StackChart({ months, chosen, links = true }) {
  const shown = windowOf(months, chosen);
  const groups = groupsIn(shown);
  const every = Math.ceil(shown.length / MAX_LABELS);
  const data = shown.map((m, i) => ({
    month: m.month, label: (shown.length - 1 - i) % every === 0 ? shortMonth(m.month) : "",
    ...Object.fromEntries(groups.map((g) => [g, Math.max(0, m.blocks[g] ?? 0) / 100])),
  }));
  const scrub = useScrub(shown.length, true);
  const read = scrub.at == null ? null : shown[scrub.at];
  const listed = read ?? shown.find((m) => m.month === chosen);
  const total = (m) => groups.reduce((sum, g) => sum + Math.max(0, m.blocks[g] ?? 0), 0);
  return (
    <>
      {listed && (
        <p className="keyhead" role="status">
          <span>{monthName(listed.month)}</span><strong className="num">{dollars(total(listed))}</strong>
        </p>
      )}
      <ul className="stackkey small" aria-label={listed ? `Groups in ${monthName(listed.month)}` : "Groups"}>
        {groups.map((g) => (
          <li key={g}>
            <i style={{ background: colourOf(g) }} />
            <span>{g}</span>
            {listed && <span className="num muted">{dollars(Math.max(0, listed.blocks[g] ?? 0))}</span>}
          </li>
        ))}
      </ul>
      <div className="chartwrap" ref={scrub.wrap} {...scrub.handlers}>
        <div className="chart" role="img" aria-label="Spending by month and group">
          <ResponsiveContainer width="100%" height={160} initialDimension={{ width: 320, height: 160 }}>
            <BarChart data={data} accessibilityLayer={false} margin={{ top: 8, right: RIGHT, bottom: 0, left: 0 }}>
              <XAxis dataKey="month" tickLine={false} axisLine={false} interval={0}
                tickFormatter={(_, i) => data[i]?.label ?? ""} tick={{ fill: "var(--muted)", fontSize: 11 }} />
              <YAxis width={AXIS} tickLine={false} axisLine={false} tickCount={4} tickFormatter={shortDollars}
                tick={{ fill: "var(--muted)", fontSize: 11 }} />
              {groups.map((g) => (
                <Bar key={g} dataKey={g} stackId="spending" fill={colourOf(g)} isAnimationActive={false}>
                  {data.map((d) => <Cell key={d.month} fillOpacity={d.month === chosen ? 1 : 0.55} />)}
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
        {links && (
          <div className="chartlinks" style={{ left: AXIS, right: RIGHT }}>
            {shown.map((m) => (m.month !== chosen
              ? <a key={m.month} href={`#/month/${m.month}`} aria-label={monthName(m.month)} />
              : <span key={m.month} />))}
          </div>
        )}
        <Reading scrub={scrub} count={shown.length} left={AXIS} right={RIGHT} bands />
      </div>
    </>
  );
}
