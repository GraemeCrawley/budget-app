// One month's own page: its savings rate, whether the month can be trusted yet, and where the money
// went. Reached from Months or a review; the arrows step to the months either side.
import { get } from "../api.js";
import BigCharges from "../components/BigCharges.jsx";
import Budgets from "../components/Budgets.jsx";
import Loading from "../components/Loading.jsx";
import Problem from "../components/Problem.jsx";
import UsualBar from "../components/UsualBar.jsx";
import DailyChart from "../components/DailyChart.jsx";
import { dollars, monthName, percent, shortDate } from "../money.js";
import { againstUsual } from "../overview.js";
import useLoad from "../useLoad.js";

function lastDay(ym) {
  const days = new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(5, 7), 0)).getUTCDate();
  return `${ym}-${String(days).padStart(2, "0")}`;
}

// Accounts that were open by the month's end but have no held range covering the whole month,
// judged the same way the server judges a month complete.
function behind(accounts, ym) {
  const first = `${ym}-01`;
  const last = lastDay(ym);
  return accounts.filter((a) => a.ranges.length > 0 && a.ranges[0][0] <= last
    && !a.ranges.some(([start, end]) => start <= first && end >= last));
}

const USUAL_MONTHS = 3;
const SAME = 2000; // within $20 of usual is "about usual"

// How far a group ran from its usual: spending more is the bad direction.
function Gap({ cents }) {
  if (Math.abs(cents) < SAME) return <span className="muted">about usual</span>;
  return <span className={`num ${cents > 0 ? "bad" : "good"}`}>{`${dollars(Math.abs(cents))} ${cents > 0 ? "above" : "below"} usual`}</span>;
}

function Arrow({ to, label, children }) {
  if (!to) {
    return <span className="arrow" aria-hidden="true">{children}</span>;
  }
  return <a className="arrow" href={`#/month/${to}`} aria-label={label}>{children}</a>;
}

export default function Month({ ym }) {
  const { data, error, retry } = useLoad(
    () => Promise.all([get("months"), get("accounts")]), []);

  if (error) return <Problem error={error} onRetry={retry} />;
  if (!data) return <Loading />;

  const [{ months, data_through: through }, { accounts }] = data;
  if (months.length === 0) {
    return (
      <div className="panel">
        <p>No months yet. Add a file to start.</p>
        <a className="btn" href="#/add">Add a file</a>
      </div>
    );
  }
  const m = months.find((x) => x.month === ym);
  if (!m) {
    return (
      <div className="panel">
        <p>There is no data for {monthName(ym)}.</p>
        <a className="btn ghost" href="#/months">See every month</a>
      </div>
    );
  }

  const index = months.indexOf(m);
  const prev = months[index - 1]?.month;
  const next = months[index + 1]?.month;
  const earliest = Object.values(through).sort()[0];
  const lagging = m.complete ? [] : behind(accounts, m.month);
  const toLook = m.uncategorised_count + m.unconfirmed_income_count;
  // "usual" is the average of up to three full months before this one
  const earlier = months.slice(0, index).filter((x) => x.complete).slice(-USUAL_MONTHS);
  const groups = againstUsual(m, earlier);
  const scale = Math.max(0, ...groups.map((g) => Math.max(g.cents, g.usual_cents ?? 0)));

  return (
    <div className="screen">
      <a className="back" href="#/months">‹ Months</a>
      <section className="hero">
        <div className="row month-row">
          <Arrow to={prev} label="Previous month">‹</Arrow>
          <strong>{monthName(m.month)}</strong>
          <Arrow to={next} label="Next month">›</Arrow>
        </div>
        <p className="big">{percent(m.savings_rate)}</p>
        <p className="lead">{m.savings_rate != null && m.savings_rate < 0 ? "You spent more than came in." : "kept of what came in."}</p>
        {m.one_off_income && <p className="note">Includes a one-off deposit, so this month runs high.</p>}
        {m.one_off_spending && <p className="note">Includes a one-off charge, so this month runs low.</p>}
        <p className="small muted">{earliest ? `Data through ${shortDate(earliest)}` : "No data yet"}</p>
      </section>

      {!m.complete && (
        <div className="note warn" role="note">
          <strong>This month is incomplete</strong>
          {lagging.map((a) => (
            <p key={a.key}>{a.name} has data through {a.data_through ? shortDate(a.data_through) : "nothing yet"}.</p>
          ))}
          <a href="#/add">Add a file</a>
        </div>
      )}
      {m.provisional && <p className="note">Includes charges not yet confirmed by a statement</p>}
      {m.changed_since_review && <p className="note">Totals changed since you reviewed this month</p>}
      {toLook > 0 && (
        <a className="btn" href={`#/review/${m.month}`}>
          {toLook === 1 ? "1 charge needs a look" : `${toLook} charges need a look`}
        </a>
      )}

      <section className="figures" aria-label="Totals">
        <div><span className="small muted">Income</span><span className="figure num">{dollars(m.income_cents)}</span></div>
        <div><span className="small muted">Spending</span><span className="figure num">{dollars(m.spending_cents)}</span></div>
        <div className="kept"><span className="small">Saved</span><span className="figure num">{dollars(m.income_cents - m.spending_cents)}</span></div>
      </section>

      <DailyChart ym={m.month} before={prev} through={m.complete ? null : earliest} />

      <section className="panel" aria-labelledby="where">
        <div className="row">
          <h2 id="where">Where it went</h2>
          <span className="small muted">{earlier.length > 0 ? "against your usual" : <span className="num">{dollars(m.spending_cents)}</span>}</span>
        </div>
        {earlier.length > 0 && (
          <p className="small muted">{`Usual is your average over the ${earlier.length === 1 ? "full month" : `${earlier.length} full months`} before, marked by the tick on each bar.`}</p>
        )}
        <div className="blocks">
          {groups.map((g) => (
            <a key={g.name} className="tap" href={`#/block/${m.month}/${encodeURIComponent(g.name)}`}>
              <span className="row">
                <strong>{g.name}</strong>
                <span className="num">{dollars(g.cents)}</span>
              </span>
              <span className="row small">
                <span className="muted amt">
                  {g.name === "Food" && g.cents > 0 ? `Out ${dollars(m.food_out_cents)}, home ${dollars(m.food_home_cents)}` : ""}
                </span>
                {g.gap_cents != null && <Gap cents={g.gap_cents} />}
              </span>
              {g.usual_cents != null && <UsualBar cents={g.cents} usual={g.usual_cents} max={scale} />}
            </a>
          ))}
        </div>
      </section>

      <Budgets months={months} ym={m.month} />

      <BigCharges ym={m.month} />
    </div>
  );
}
