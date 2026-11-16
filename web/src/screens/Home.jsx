// Home: the ten-second look. Last month's savings rate against the target, with the three-month
// figure beside it; whether anything is waiting; and what moved against the month before, as
// figures rather than sentences. Nothing here depends on a chosen month.
import { get } from "../api.js";
import BudgetWatch from "../components/BudgetWatch.jsx";
import Loading from "../components/Loading.jsx";
import MoneyChart from "../components/MoneyChart.jsx";
import Problem from "../components/Problem.jsx";
import RateChart from "../components/RateChart.jsx";
import StackChart from "../components/StackChart.jsx";
import { dollars, monthName, monthOnly, percent, shortDate } from "../money.js";
import { groupMoves, lastTwo, needingALook, pointsFromTarget, pooled, recent } from "../overview.js";
import { TARGET } from "../target.js";
import useLoad from "../useLoad.js";

const AVERAGE_MONTHS = 3;
const CHART_MONTHS = 12;

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// Each spending group keeps one colour everywhere it appears.
const TILE = { Bills: "orange", Food: "yellow", "Everything else": "blue", "Big purchases": "pink", Subscriptions: "mint" };
const tileColour = (name) => TILE[name] || "plain";

function verdict(points, share) {
  if (points == null) return null;
  const target = percent(share);
  if (points === 0) return `On your ${target} target`;
  return `${plural(Math.abs(points), "point")} ${points > 0 ? "above" : "below"} your ${target} target`;
}

// "up $120", "down $40", or "no change" under a dollar.
function moved(cents) {
  if (Math.abs(cents) < 100) return { words: "no change", way: "" };
  return { words: `${cents > 0 ? "up" : "down"} ${dollars(Math.abs(cents))}`, way: cents > 0 ? "up" : "down" };
}

// More coming in is good; more going out is not.
function Move({ label, cents, moreIsGood = false }) {
  const m = moved(cents);
  const tone = m.way === "" ? "" : (m.way === "up") === moreIsGood ? "good" : "bad";
  return <li><span>{label}</span><span className={`num ${tone}`}>{m.words}</span></li>;
}

export default function Home() {
  const { data, error, retry } = useLoad(() => get("months"), []);
  if (error) return <Problem error={error} onRetry={retry} />;
  if (!data) return <Loading />;

  const { months, data_through: through } = data;
  const target = data.target ?? TARGET; // set on the Plan screen
  if (months.length === 0) {
    return (
      <div className="panel">
        <p>No months yet. Add a file to start.</p>
        <a className="btn" href="#/add">Add a file</a>
      </div>
    );
  }
  const { last: full, before } = lastTwo(months);
  const last = full ?? months.at(-1); // nothing full yet: show what there is, marked
  const average = pooled(recent(months, AVERAGE_MONTHS));
  const groups = groupMoves(last, before);
  const movers = before
    ? groups.filter((g) => Math.abs(g.moved_cents) >= 100)
      .sort((a, b) => Math.abs(b.moved_cents) - Math.abs(a.moved_cents)).slice(0, 3)
    : [];
  const charted = recent(months, CHART_MONTHS);
  const toLookCount = needingALook(months).reduce((n, m) => n + m.count, 0);
  const earliest = Object.values(through || {}).sort()[0];
  const rate = last.savings_rate;
  const kept = last.income_cents - last.spending_cents;
  const marks = [!last.complete && "not a full month yet", last.provisional && "includes charges not yet on a statement"]
    .filter(Boolean);

  return (
    <div className="screen">
      <section className="hero">
        <div className="row">
          <strong>Savings rate</strong>
          <span className="pill">{monthName(last.month)}</span>
        </div>
        <p className="big">{percent(rate)}</p>
        <p className="lead">{rate != null && rate < 0 ? "You spent more than came in." : "kept of what came in."}</p>
        {verdict(pointsFromTarget(rate, target), target) && <p className="verdict">{verdict(pointsFromTarget(rate, target), target)}</p>}
        <p className="small">Last {plural(average.count, "month")}: {percent(average.rate)}</p>
        {marks.length > 0 && <p className="small">{marks.join(", ")}</p>}
        <RateChart months={charted} links={false} />
      </section>

      <a className="figures" href={`#/month/${last.month}`} aria-label={`${monthName(last.month)} in full`}>
        <div><span className="small muted">Income</span><span className="figure num">{dollars(last.income_cents)}</span></div>
        <div><span className="small muted">Spending</span><span className="figure num">{dollars(last.spending_cents)}</span></div>
        <div className="kept"><span className="small">Saved</span><span className="figure num">{dollars(kept)}</span></div>
      </a>

      <section className="panel look" role="region" aria-label="Waiting for you">
        <h2>Waiting for you</h2>
        {toLookCount > 0
          ? <a className="btn" href="#/review">{plural(toLookCount, "charge")} to check</a>
          : <p className="muted">Nothing. Every charge is checked.</p>}
      </section>

      <BudgetWatch months={months} />

      {before && (
        <section className="panel" role="region" aria-label="What changed">
          <div className="row"><h2>What changed</h2><span className="small muted">against {monthOnly(before.month)}</span></div>
          <ul className="metrics">
            <Move label="Income" cents={last.income_cents - before.income_cents} moreIsGood />
            <Move label="Spending" cents={last.spending_cents - before.spending_cents} />
            {movers.map((g) => <Move key={g.name} label={g.name} cents={g.moved_cents} />)}
          </ul>
        </section>
      )}

      <section className="panel" role="region" aria-label="Where it went">
        <div className="row"><h2>Where {monthOnly(last.month)} went</h2><span className="small muted num">{dollars(last.spending_cents)}</span></div>
        <ul className="tiles">
          {groups.map((g) => (
            <li key={g.name}>
              <a className={`tile ${tileColour(g.name)}`} href={`#/block/${last.month}/${encodeURIComponent(g.name)}`}>
                <strong>{g.name}</strong>
                <span className="amount num">{dollars(g.cents)}</span>
              </a>
            </li>
          ))}
        </ul>
      </section>

      {charted.length > 1 && (
        <section className="panel" role="region" aria-label="Spending by group">
          <h2>Spending by group</h2>
          <StackChart months={charted} chosen={last.month} links={false} />
        </section>
      )}

      <section className="panel">
        <h2>Income and spending, month by month</h2>
        <MoneyChart months={charted} links={false} />
        <a className="btn ghost" href="#/months">See every month</a>
        <p className="small muted">{earliest ? `Data through ${shortDate(earliest)}` : "No data yet"}</p>
      </section>
    </div>
  );
}
