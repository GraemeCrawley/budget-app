// Review a month, or with no month, everything still to check across all months: place what could not be categorised, confirm income that was only a guess,
// look over what was recognised, then mark the month reviewed. After each answer the list is
// fetched again, so what is shown is what the server holds.
import { useState } from "react";
import { get, send } from "../api.js";
import CategoryPicker from "../components/CategoryPicker.jsx";
import ChargeRow from "../components/ChargeRow.jsx";
import Loading from "../components/Loading.jsx";
import PlaceGroup from "../components/PlaceGroup.jsx";
import Problem from "../components/Problem.jsx";
import Sheet from "../components/Sheet.jsx";
import { FORGOTTEN, oldAndSmall } from "../forgotten.js";
import { exact, monthName } from "../money.js";
import { go } from "../router.js";
import useLoad from "../useLoad.js";

export default function Review({ ym }) {
  const path = ym ? `review?month=${ym}` : "review";
  const { data, error, retry } = useLoad(() => get(path), [ym]);
  const [fresh, setFresh] = useState(null);
  const [stale, setStale] = useState(null); // saved, but the fresh list could not be loaded
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(null);
  const [picking, setPicking] = useState(null); // {charge, group}: the charge whose category is being chosen
  const [recognisedOpen, setRecognisedOpen] = useState(null); // null = the default for this review
  const [openCategory, setOpenCategory] = useState(null);

  if (error) return <Problem error={error} onRetry={retry} />;
  if (!data) return <Loading />;
  const review = fresh ?? data;
  if (stale) {
    return <Problem error={stale} message="Saved, but couldn't reload." onRetry={reload} retryLabel="Retry" />;
  }
  const nothing = review.unplaced.length === 0 && review.unconfirmed_income.length === 0;

  // One save step (the answer, then the list again). A failure keeps the step so "Try again"
  // sends exactly what failed; the list on screen stays as it was.
  async function run(step) {
    setBusy(true);
    setFailed(null);
    try {
      await step();
    } catch (e) {
      setFailed({ error: e, again: () => run(step) });
    } finally {
      setBusy(false);
    }
  }

  // A failed reload is not a failed save: the answer is in, so Retry only fetches the list again.
  async function reload() {
    setBusy(true);
    try {
      setFresh(await get(path));
      setStale(null);
    } catch (e) {
      setStale(e);
    } finally {
      setBusy(false);
    }
  }
  const refetch = reload;
  const open = (c) => go(`/charge/${c.id}`);

  const place = (charge, group, category) => run(async () => {
    if (group) await send("POST", `transactions/${charge.id}/merchant-rule`, { kind: "spending", category });
    else await send("PUT", `transactions/${charge.id}/override`, { category });
    await refetch();
  });
  // Picking "Can't remember" for a shop files each of its charges by itself, so the shop gets no
  // rule and its next charge is asked about.
  const forget = (charges) => run(async () => {
    for (const c of charges) await send("PUT", `transactions/${c.id}/override`, { kind: "spending", category: FORGOTTEN });
    await refetch();
  });
  const old = ym ? [] : oldAndSmall(review.unplaced);
  const confirm = (charge, kind) => run(async () => {
    await send("PUT", `transactions/${charge.id}/override`, { kind });
    await refetch();
  });
  const done = () => run(async () => {
    await send("POST", `months/${ym}/reviewed`);
    go(`/month/${ym}`);
  });

  const showRecognised = recognisedOpen ?? nothing;

  return (
    <div className="screen">
      <a className="back" href={ym ? `#/month/${ym}` : "#/"}>‹ {ym ? monthName(ym) : "Home"}</a>
      <h1>{ym ? `Review ${monthName(ym)}` : "Charges to check"}</h1>
      {!ym && !nothing && <p className="small muted">Every month, in one list. An answer for a shop covers all its charges.</p>}

      {failed && (
        <Problem error={failed.error} message="Couldn't save that. Try again." onRetry={failed.again} retryLabel="Try again" />
      )}

      {nothing && <section className="panel"><h2>{ym ? "Nothing needs placing" : "All checked. Nothing is waiting."}</h2></section>}

      {review.unplaced.length > 0 && (
        <section className="panel" aria-labelledby="to-place">
          <h2 id="to-place">{`${review.unplaced.length} to place`}</h2>
          {old.length > 0 && (
            <div className="forget">
              <p className="small muted">
                {`${old.length} of these are over three months old and under $200. If they are past remembering, file them under the "${FORGOTTEN}" category: they still count as spending, and you can find and change them later.`}
              </p>
              <button type="button" className="btn ghost" disabled={busy} onClick={() => forget(old)}>
                {`Can't remember the ${old.length} old, small ones`}
              </button>
            </div>
          )}
          <ul className="plain groups">
            {review.unplaced.map((g) => (
              // a merchant with charges and refunds comes as two groups, one of each sign
              <PlaceGroup key={`${g.merchant || "none"}|${g.charges[0]?.amount_cents > 0 ? "in" : "out"}`}
                group={g} disabled={busy} onOpen={open} onForget={forget}
                onChoose={(charge, group) => setPicking({ charge, group })} />
            ))}
          </ul>
        </section>
      )}

      {review.unconfirmed_income.length > 0 && (
        <section className="panel" aria-labelledby="income">
          <h2 id="income">Is this income?</h2>
          <ul className="plain">
            {review.unconfirmed_income.map((c) => (
              <li key={c.id} data-testid="income-row" className="income-row">
                <ChargeRow charge={c} detail onOpen={open} />
                <div className="group-actions">
                  <button type="button" className="btn" disabled={busy} onClick={() => confirm(c, "income")}>Yes, income</button>
                  <button type="button" className="btn ghost" disabled={busy} onClick={() => confirm(c, "transfer")}>No</button>
                  <a className="btn ghost" href={`#/charge/${c.id}`}>Something else</a>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {review.recognised.length > 0 && (
        <section className="panel">
          <button type="button" className="fold" aria-expanded={showRecognised} onClick={() => setRecognisedOpen(!showRecognised)}>
            <h2>{`Recognised (${review.recognised.length})`}</h2>
            <span className="muted" aria-hidden="true">{showRecognised ? "Hide" : "Show"}</span>
          </button>
          {showRecognised && (
            <ul className="plain">
              {review.recognised.map((cat) => (
                <li key={cat.category}>
                  <button type="button" className="fold sub" aria-expanded={openCategory === cat.category}
                    onClick={() => setOpenCategory(openCategory === cat.category ? null : cat.category)}>
                    <span>{cat.category}</span>
                    <span className="num muted">{exact(cat.cents)}</span>
                  </button>
                  {openCategory === cat.category && (
                    <ul className="plain">
                      {cat.charges.map((c) => <li key={c.id}><ChargeRow charge={c} detail onOpen={open} /></li>)}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {ym
        ? <button type="button" className="btn" disabled={busy} onClick={done}>Done reviewing</button>
        : <a className="btn" href="#/">{nothing ? "See how the month went" : "Finish later"}</a>}

      {picking && (
        <Sheet title={`Category for ${picking.group ? picking.group.merchant : picking.charge.description}`}
          onClose={() => setPicking(null)}>
          <CategoryPicker value={null} onPick={(category) => {
            const { charge, group } = picking;
            setPicking(null);
            if (category === FORGOTTEN) forget(group ? group.charges : [charge]);
            else place(charge, group, category);
          }} />
        </Sheet>
      )}
    </div>
  );
}
