// Every charge in one month. Spending by default; "Everything" adds income, savings and money
// moved between accounts. Newest first or biggest first, and a box to narrow by shop or category.
import { useState } from "react";
import { monthCharges } from "../charges.js";
import ChargeRow from "../components/ChargeRow.jsx";
import Loading from "../components/Loading.jsx";
import Problem from "../components/Problem.jsx";
import { dollars, monthName } from "../money.js";
import { go } from "../router.js";
import useLoad from "../useLoad.js";

const newest = (a, b) => b.date.localeCompare(a.date) || b.id - a.id;
const biggest = (a, b) => Math.abs(b.amount_cents) - Math.abs(a.amount_cents) || newest(a, b);
const isSpending = (c) => Boolean(c.block);

function Pick({ label, value, options, onPick }) {
  return (
    <div className="choices small" role="group" aria-label={label}>
      {options.map(([v, words]) => (
        <button key={v} type="button" aria-pressed={value === v} onClick={() => onPick(v)}>{words}</button>
      ))}
    </div>
  );
}

export default function Charges({ ym }) {
  const { data, error, retry } = useLoad(() => monthCharges(ym), [ym]);
  const [show, setShow] = useState("spending");
  const [order, setOrder] = useState("newest");
  const [words, setWords] = useState("");

  if (error) return <Problem error={error} onRetry={retry} />;
  if (!data) return <Loading />;

  const wanted = words.trim().toLowerCase();
  const listed = data.transactions
    .filter((c) => show === "everything" || isSpending(c))
    .filter((c) => !wanted || [c.merchant, c.description, c.category, c.account_name]
      .some((text) => (text || "").toLowerCase().includes(wanted)))
    .sort(order === "biggest" ? biggest : newest);
  const spent = -listed.filter(isSpending).reduce((n, c) => n + c.amount_cents, 0);

  return (
    <div className="screen">
      <a className="back" href={`#/month/${ym}`}>‹ {monthName(ym)}</a>
      <section className="panel">
        <h1>All charges</h1>
        <span className="small muted">{monthName(ym)}</span>
        <Pick label="Show" value={show} onPick={setShow} options={[["spending", "Spending"], ["everything", "Everything"]]} />
        <Pick label="Order" value={order} onPick={setOrder} options={[["newest", "Newest first"], ["biggest", "Biggest first"]]} />
        <label className="budget-edit">
          <span className="small muted">Narrow by shop, category or account</span>
          <input type="search" value={words} onChange={(e) => setWords(e.target.value)} />
        </label>
        <p className="small muted" role="status">
          {listed.length === 1 ? "1 charge" : `${listed.length} charges`}, spending {dollars(spent)}
        </p>
      </section>
      <section className="panel" aria-label="Charges">
        {listed.length === 0 ? <p className="muted">Nothing matches.</p> : (
          <div className="charges">
            {listed.map((c) => <ChargeRow key={c.id} charge={c} onOpen={() => go(`/charge/${c.id}`)} />)}
          </div>
        )}
      </section>
    </div>
  );
}
