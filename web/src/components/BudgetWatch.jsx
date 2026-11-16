// Home's line on budgets: for the latest month, which budgets have run over and by how much, or
// that all are on track. Left out when there are no budgets.
import { get } from "../api.js";
import { dollars, monthOnly } from "../money.js";
import { budgetRows } from "../plan.js";
import useLoad from "../useLoad.js";

export default function BudgetWatch({ months }) {
  const { data } = useLoad(() => get("plan"), []); // a failure here just leaves the section out
  const budgets = data?.budgets;
  const latest = months.at(-1);
  if (!budgets || budgets.length === 0 || !latest) return null;
  const rows = budgetRows(budgets, months, latest.month);
  const over = rows.filter((r) => r.left_cents < 0);
  const month = monthOnly(latest.month);
  return (
    <section className="panel" role="region" aria-label="Budgets">
      <div className="row">
        <h2>Budgets</h2>
        <a className="small" href={`#/month/${latest.month}`}>{month} in full</a>
      </div>
      {over.length === 0 ? (
        <p className="muted">{rows.length === 1 ? `Your budget is on track in ${month}.` : `All ${rows.length} budgets are on track in ${month}.`}</p>
      ) : (
        <>
          <p>{over.length} of {rows.length} over in {month}{latest.complete ? "" : " so far"}.</p>
          <ul className="metrics">
            {over.map((r) => (
              <li key={r.category}>
                <span>{r.category}{r.period === "year" ? " (this year)" : ""}</span>
                <span className="num bad">{dollars(-r.left_cents)} over</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
