// Every month, newest first. Each row opens that month's own page.
import { get } from "../api.js";
import Loading from "../components/Loading.jsx";
import Problem from "../components/Problem.jsx";
import { dollars, monthName, percent } from "../money.js";
import useLoad from "../useLoad.js";

export default function Months() {
  const { data, error, retry } = useLoad(() => get("months"), []);
  if (error) return <Problem error={error} onRetry={retry} />;
  if (!data) return <Loading />;
  if (data.months.length === 0) {
    return (
      <div className="panel">
        <p>No months yet. Add a file to start.</p>
        <a className="btn" href="#/add">Add a file</a>
      </div>
    );
  }
  return (
    <div className="screen">
      <section className="panel">
        <h1>Months</h1>
        <div className="blocks">
          {[...data.months].reverse().map((m) => {
            const toLook = m.uncategorised_count + m.unconfirmed_income_count;
            return (
              <a key={m.month} className="tap row" href={`#/month/${m.month}`}>
                <span className="what">
                  <strong>{monthName(m.month)}</strong>
                  <span className="small muted amt">In {dollars(m.income_cents)} · Out {dollars(m.spending_cents)}</span>
                  {(!m.complete || toLook > 0) && (
                    <span className="small mark">
                      {[!m.complete && "so far", toLook > 0 && `${toLook} to look at`].filter(Boolean).join(" · ")}
                    </span>
                  )}
                </span>
                <span className="figure num">{percent(m.savings_rate)}</span>
              </a>
            );
          })}
        </div>
      </section>
    </div>
  );
}
