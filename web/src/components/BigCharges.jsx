// The month's biggest single charges: the first place to look when a month ran high.
import { biggest, monthCharges } from "../charges.js";
import { go } from "../router.js";
import useLoad from "../useLoad.js";
import ChargeRow from "./ChargeRow.jsx";

const SHOWN = 5;

export default function BigCharges({ ym }) {
  const { data } = useLoad(() => monthCharges(ym), [ym]);
  const top = data ? biggest(data.transactions, SHOWN) : [];
  const count = data ? data.transactions.filter((t) => t.block).length : 0;
  if (top.length === 0) return null;
  return (
    <section className="panel" aria-labelledby="biggest">
      <h2 id="biggest">Biggest charges</h2>
      <ul className="plain">
        {top.map((c) => <li key={c.id}><ChargeRow charge={c} onOpen={() => go(`/charge/${c.id}`)} /></li>)}
      </ul>
      <a className="btn ghost" href={`#/charges/${ym}`}>{count === 1 ? "See the 1 charge" : `See all ${count} charges`}</a>
    </section>
  );
}
