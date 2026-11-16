// Plan: the savings-rate target, and a budget for any category by the month or by the year. Each
// category shows its usual (the average of the last three full months) as a guide for the amount.
import { useState } from "react";
import { get, send } from "../api.js";
import Loading from "../components/Loading.jsx";
import Problem from "../components/Problem.jsx";
import { dollars, percent } from "../money.js";
import { pooled, recent } from "../overview.js";
import { usualByCategory } from "../plan.js";
import useLoad from "../useLoad.js";

const STEP = 0.01;
const MAX_TARGET = 0.9;
const PERIODS = [["month", "A month"], ["year", "A year"]];

function BudgetEditor({ category, budget, usual, onSave, onRemove, busy }) {
  // with no budget yet, the usual amount is filled in, ready to save or change
  const [amount, setAmount] = useState(budget ? String(budget.cents / 100) : usual ? String(Math.round(usual / 100)) : "");
  const [period, setPeriod] = useState(budget?.period ?? "month");
  const cents = Math.round(Number(amount) * 100);
  const valid = amount.trim() !== "" && Number.isFinite(cents) && cents > 0;
  return (
    <form className="budget-edit" onSubmit={(e) => { e.preventDefault(); if (valid) onSave(cents, period); }}>
      <label>
        <span className="small muted">Budget for {category}, in dollars</span>
        <input type="text" inputMode="decimal" value={amount} placeholder="0"
          onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ""))} />
      </label>
      <div className="choices small" role="group" aria-label="For">
        {PERIODS.map(([value, words]) => (
          <button key={value} type="button" aria-pressed={period === value} onClick={() => setPeriod(value)}>{words}</button>
        ))}
      </div>
      <div className="row">
        <button type="submit" className="btn" disabled={!valid || busy}>Save budget</button>
        {budget && <button type="button" className="btn ghost" disabled={busy} onClick={onRemove}>Remove</button>}
      </div>
    </form>
  );
}

export default function Plan() {
  const { data, error, retry } = useLoad(() => Promise.all([get("months"), get("plan"), get("categories")]), []);
  const [plan, setPlan] = useState(null); // the plan after a change made here
  const [open, setOpen] = useState(null); // the category being edited
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState("");

  if (error) return <Problem error={error} onRetry={retry} />;
  if (!data) return <Loading />;

  const [{ months }, loaded, { categories }] = data;
  const { target, budgets } = plan ?? loaded;
  const usual = usualByCategory(months);
  const held = Object.fromEntries(budgets.map((b) => [b.category, b]));
  const names = [...new Set([...categories, ...Object.keys(usual), ...Object.keys(held)])]
    .filter((name) => name !== "Uncategorised")
    .sort((a, b) => Boolean(held[b]) - Boolean(held[a]) || (usual[b] ?? 0) - (usual[a] ?? 0) || a.localeCompare(b));
  const average = pooled(recent(months, 3));
  const income = average?.income_cents > 0 ? average.income_cents : null; // an average month's income
  // a monthly amount as a share of an average month's income: ", 21% of income"
  const share = (cents) => (income ? `, ${percent(cents / income)} of income` : "");
  const monthly = (b) => (b.period === "year" ? Math.round(b.cents / 12) : b.cents);

  const change = async (method, path, body, done) => {
    setBusy(true);
    setSaid("");
    try {
      setPlan(await send(method, path, body));
      setOpen(null);
      setSaid(done);
    } catch (e) {
      setSaid(e?.detail || "That did not save.");
    }
    setBusy(false);
  };
  const move = (by) => change("PUT", "plan/target",
    { target: Math.round(Math.max(0, Math.min(MAX_TARGET, target + by)) * 100) / 100 }, "");

  return (
    <div className="screen">
      <h1>Plan</h1>
      <section className="panel" role="region" aria-label="Savings target">
        <h2>Savings target</h2>
        <div className="stepper">
          <button type="button" aria-label="Lower the target" disabled={busy || target <= 0} onClick={() => move(-STEP)}>−</button>
          <strong className="figure num" aria-live="polite">{percent(target)}</strong>
          <button type="button" aria-label="Raise the target" disabled={busy || target >= MAX_TARGET} onClick={() => move(STEP)}>+</button>
        </div>
        {income && <p className="lead">About <strong className="num">{dollars(Math.round(target * income))}</strong> a month, on your average income of {dollars(income)}.</p>}
        <p className="small muted">The share of income you aim to keep each month. Home measures every month against it.</p>
        {average?.count > 0 && <p className="small muted">Your last {average.count === 1 ? "full month" : `${average.count} full months`}: {percent(average.rate)}.</p>}
      </section>

      <section className="panel" role="region" aria-label="Budgets">
        <h2>Budgets</h2>
        <p className="small muted">Tap a category to give it a budget, by the month or by the year. Each month's page then shows what is left.</p>
        {said && <p className="small" role="status">{said}</p>}
        <ul className="plain">
          {names.map((name) => (
            <li key={name}>
              <button type="button" className="row merchant" aria-expanded={open === name}
                onClick={() => setOpen(open === name ? null : name)}>
                <span className="stack">
                  {name}
                  <span className="small muted"> {usual[name] ? `usually ${dollars(usual[name])} a month${share(usual[name])}` : "nothing lately"}</span>
                </span>
                <span className={held[name] ? "stack right nowrap" : "small muted nowrap"}>
                  {held[name] ? (
                    <>
                      <span className="num">{`${dollars(held[name].cents)} a ${held[name].period}`}</span>
                      {income && <span className="small muted">{percent(monthly(held[name]) / income)} of income</span>}
                    </>
                  ) : "No budget"}
                </span>
              </button>
              {open === name && (
                <BudgetEditor category={name} budget={held[name]} usual={usual[name]} busy={busy}
                  onSave={(cents, period) => change("PUT", "plan/budgets", { category: name, cents, period }, `Saved the budget for ${name}.`)}
                  onRemove={() => change("DELETE", "plan/budgets", { category: name }, `Removed the budget for ${name}.`)} />
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
