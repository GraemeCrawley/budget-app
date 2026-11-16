// One block in one month: how it moved over the months, the biggest merchants, and every charge.
// Picking one of its categories shows that category across the months instead, with its charges;
// Food as a whole is drawn as eating out against eating at home. Tapping a merchant narrows the
// charges to that merchant.
import { useState } from "react";
import { get } from "../api.js";
import BlockChart, { SPLIT, windowOf } from "../components/BlockChart.jsx";
import ChargeRow from "../components/ChargeRow.jsx";
import Loading from "../components/Loading.jsx";
import Problem from "../components/Problem.jsx";
import { dollars, monthName } from "../money.js";
import { go } from "../router.js";
import useLoad from "../useLoad.js";

const merchantOf = (c) => c.merchant || c.description;

function topMerchants(charges) {
  const groups = new Map();
  for (const c of charges) {
    const name = merchantOf(c);
    const g = groups.get(name) ?? { name, cents: 0, count: 0 };
    g.cents -= c.amount_cents;
    g.count += 1;
    groups.set(name, g);
  }
  return [...groups.values()].sort((a, b) => b.cents - a.cents || a.name.localeCompare(b.name)).slice(0, 5);
}

// The categories this block held in the months the chart shows, biggest in the chosen month first.
function categoriesOf(months, m, block) {
  const now = m.categories?.[block] ?? {};
  const names = new Set(windowOf(months, m.month).flatMap((x) => Object.entries(x.categories?.[block] ?? {})
    .filter(([, cents]) => cents > 0).map(([name]) => name)));
  return [...names].sort((a, b) => (now[b] ?? 0) - (now[a] ?? 0) || a.localeCompare(b));
}

// The category last looked at in each block, so stepping to another month keeps it.
const FIRST = 4; // categories offered before "more"
const picked = {};
export const forgetPicked = () => Object.keys(picked).forEach((k) => delete picked[k]);

const newestFirst = (a, b) => b.date.localeCompare(a.date) || b.id - a.id;

export default function Block({ ym, block }) {
  const { data, error, retry } = useLoad(() => Promise.all([
    get("months"),
    get(`transactions?month=${ym}&block=${encodeURIComponent(block)}`),
  ]), [ym, block]);
  const [only, setOnly] = useState(null); // the merchant whose charges alone are listed
  const [chosenCategory, setChosenCategory] = useState(() => picked[block] ?? null);
  const [all, setAll] = useState(false); // every category offered, not just the biggest few
  const pick = (name) => { picked[block] = name; setChosenCategory(name); setOnly(null); };

  if (error) return <Problem error={error} onRetry={retry} />;
  if (!data) return <Loading />;

  const [{ months }, { transactions }] = data;
  const m = months.find((x) => x.month === ym);
  const back = <a className="btn ghost" href={`#/month/${ym}`}>Back to {monthName(ym)}</a>;
  if (!m || !(block in m.blocks)) {
    return <div className="panel"><p>There is nothing to show for {block} in {monthName(ym)}.</p>{back}</div>;
  }
  const categories = categoriesOf(months, m, block);
  const category = categories.includes(chosenCategory) ? chosenCategory : null;
  const amount = category ? m.categories?.[block]?.[category] ?? 0 : m.blocks[block];
  const split = block === "Food" && !category;
  // the biggest few, plus the picked one if it is further down; the rest sit behind "more"
  const offered = all ? categories : categories.filter((name, i) => i < FIRST || name === category);
  const charges = transactions.filter((c) => !category || c.category === category).sort(newestFirst);
  const merchants = topMerchants(charges);
  const listed = only ? charges.filter((c) => merchantOf(c) === only) : charges;

  return (
    <div className="screen">
      <a className="back" href={`#/month/${ym}`}>‹ {monthName(ym)}</a>
      <section className="panel">
        <div className="row"><h1>{block}</h1><span className="figure num">{dollars(amount)}</span></div>
        <span className="small muted">{category ? `${category}, ${monthName(ym)}` : monthName(ym)}</span>
        {categories.length > 1 && (
          <div className="choices small" role="group" aria-label="Show">
            <button type="button" aria-pressed={!category} onClick={() => pick(null)}>All</button>
            {offered.map((name) => (
              <button key={name} type="button" aria-pressed={category === name} onClick={() => pick(name)}>{name}</button>
            ))}
            {categories.length > offered.length && (
              <button type="button" className="more" onClick={() => setAll(true)}>{categories.length - offered.length} more</button>
            )}
            {all && categories.length > FIRST && (
              <button type="button" className="more" onClick={() => setAll(false)}>Fewer</button>
            )}
          </div>
        )}
        <BlockChart months={months} block={block} chosen={ym} category={category} split={split} />
        {split && (
          <div className="pair">
            {SPLIT.map((s) => (
              <div key={s.key}>
                <span className="small muted"><i className="dot" style={{ background: s.colour }} />{s.name}</span>
                <span className="figure num">{dollars(s.of(m))}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {charges.length === 0 ? (
        <p className="panel">No charges in {category ?? block} this month.</p>
      ) : (
        <>
          <section className="panel" aria-label="Top merchants">
            <h2>Top merchants</h2>
            <ul className="plain">
              {merchants.map((g) => (
                <li key={g.name}>
                  <button type="button" className={`row merchant${only === g.name ? " on" : ""}`}
                    aria-pressed={only === g.name} onClick={() => setOnly(only === g.name ? null : g.name)}>
                    <span>
                      {g.name}
                      {g.count > 1 && <span className="small muted"> {g.count} charges</span>}
                    </span>
                    <span className="num">{dollars(g.cents)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <section className="panel" aria-label="Charges">
            <div className="row">
              <h2>{only ? `Charges at ${only}` : "Charges"}</h2>
              {only && <button type="button" className="link" onClick={() => setOnly(null)}>Show all</button>}
            </div>
            <div className="charges">
              {listed.map((c) => <ChargeRow key={c.id} charge={c} onOpen={() => go(`/charge/${c.id}`)} />)}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
