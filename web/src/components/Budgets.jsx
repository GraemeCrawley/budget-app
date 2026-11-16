// The month page's budgets: each budget against what was spent, monthly ones against the month and
// yearly ones against the year so far. Shown only when there are budgets.
import { get } from "../api.js";
import { dollars } from "../money.js";
import { budgetRows } from "../plan.js";
import useLoad from "../useLoad.js";
import UsualBar from "./UsualBar.jsx";

export default function Budgets({ months, ym }) {
  const { data } = useLoad(() => get("plan"), []); // a failure here just leaves the section out
  const budgets = data?.budgets;
  if (!budgets || budgets.length === 0) return null;
  const rows = budgetRows(budgets, months, ym);
  return (
    <section className="panel" role="region" aria-label="Budgets">
      <div className="row"><h2>Budgets</h2><a className="small" href="#/plan">Change</a></div>
      <ul className="plain budgets">
        {rows.map((r) => (
          <li key={r.category}>
            <span className="row">
              <strong>{r.category}</strong>
              <span className="num">{dollars(r.spent_cents)} of {dollars(r.budget_cents)}</span>
            </span>
            <span className="row small">
              <span className="muted">{r.period === "year" ? "this year so far" : "this month"}</span>
              <span className={`num ${r.left_cents < 0 ? "bad" : "good"}`}>
                {r.left_cents < 0 ? `${dollars(-r.left_cents)} over` : `${dollars(r.left_cents)} left`}
              </span>
            </span>
            <UsualBar cents={r.spent_cents} usual={r.budget_cents} max={Math.max(r.spent_cents, r.budget_cents)} />
          </li>
        ))}
      </ul>
    </section>
  );
}
