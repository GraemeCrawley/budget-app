// One charge: what the bank said, how it is counted and why, and every way to correct it. After any
// change the screen shows what the server returned, so a failed save leaves the shown state alone.
import { useState } from "react";
import { get, send } from "../api.js";
import CategoryPicker from "../components/CategoryPicker.jsx";
import Loading from "../components/Loading.jsx";
import Problem from "../components/Problem.jsx";
import Sheet from "../components/Sheet.jsx";
import { FORGOTTEN } from "../forgotten.js";
import { exact, monthName, shortDate } from "../money.js";
import useLoad from "../useLoad.js";

const SPENDING_LIKE = ["spending", "bucket", "offset"];
const COUNTED = { spending: "Spending", bucket: "Spending (bucket)", offset: "Spending (offset)",
  income: "Income", transfer: "Not counted", saving: "Saved" };

export default function Charge({ id }) {
  const { data, error, retry } = useLoad(() => get(`transactions/${id}`), [id]);
  const [tx, setTx] = useState(null); // what the server last returned after a change
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(null);
  const [picking, setPicking] = useState(false);
  const [asking, setAsking] = useState(null); // a category picked, waiting for just-this-or-all
  const [offer, setOffer] = useState(null); // a category just set, the merchant rule on offer
  const [stale, setStale] = useState(null); // saved, but the fresh copy could not be loaded

  if (error) return <Problem error={error} onRetry={retry} />;
  if (!data) return <Loading />;
  const t = tx ?? data;
  const path = `transactions/${t.id}`;

  // Run one save step (the request and what follows it). If it fails, the same step is kept so
  // "Try again" resends exactly what failed.
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

  async function reload() {
    try {
      setTx(await get(path));
      setStale(null);
    } catch (e) {
      setStale(e);
    }
  }

  // The override body for picking a category: a charge not counted as spending becomes spending.
  const categoryBody = (category) => (SPENDING_LIKE.includes(t.kind) ? { category } : { kind: "spending", category });

  // `offerFor` is the category to offer as a merchant rule once this succeeds; any other change clears the offer.
  const override = (body, offerFor = null) => run(async () => {
    const next = await send("PUT", `${path}/override`, body);
    setTx({ merchant_charges: t.merchant_charges, ...next });
    setAsking(null);
    setOffer(offerFor);
  });

  const undo = () => run(async () => {
    const next = await send("DELETE", `${path}/override`);
    setTx({ merchant_charges: t.merchant_charges, ...next });
    setOffer(null);
  });

  const merchantRule = (category) => run(async () => {
    const kind = SPENDING_LIKE.includes(t.kind) ? t.kind : "spending";
    await send("POST", `${path}/merchant-rule`, { kind, category });
    setAsking(null);
    setOffer(null);
    await reload();
  });

  function chosen(category) {
    setPicking(false);
    setOffer(null);
    if (t.merchant && t.merchant_charges > 1) {
      setAsking(category);
      return;
    }
    override(categoryBody(category), t.merchant ? category : null);
  }

  if (stale) {
    return <Problem error={stale} message="Saved, but couldn't reload this charge. Try again." onRetry={reload} />;
  }

  const month = t.date.slice(0, 7);
  const backHref = t.block ? `#/block/${month}/${encodeURIComponent(t.block)}` : `#/month/${month}`;
  const backLabel = t.block ? `${t.block}, ${monthName(month)}` : monthName(month);
  const spending = SPENDING_LIKE.includes(t.kind);
  // Only while the charge still has that category and is still counted as spending.
  const showOffer = offer && !asking && t.merchant && spending && t.category === offer;

  return (
    <div className="screen">
      <a className="back" href={backHref}>‹ {backLabel}</a>
      <section className="panel">
        <h1 className="num">{exact(t.amount_cents)}</h1>
        {t.merchant && <p className="muted">{t.merchant}</p>}
        <dl className="facts">
          <div><dt>Date</dt><dd>{`${shortDate(t.date)}, ${t.date.slice(0, 4)}`}</dd></div>
          <div><dt>Bank description</dt><dd>{t.description}</dd></div>
          <div><dt>Account</dt><dd>{t.account_name}</dd></div>
          <div><dt>Category</dt><dd>{t.category || "None"}</dd></div>
          <div><dt>Counted as</dt><dd>{COUNTED[t.kind] ?? t.kind}</dd></div>
        </dl>
        <p className="small muted">{`Why: ${t.why}`}</p>
        {t.provisional && <p className="note">Not yet confirmed by a statement</p>}
        {t.guessed && t.kind === "income" && <p className="note">This looks like income. Is it?</p>}
      </section>

      {failed && (
        <Problem error={failed.error} message="Couldn't save that. Try again." onRetry={failed.again}
          retryLabel="Try again" />
      )}

      {asking && (
        <section className="panel" aria-label="Apply to which charges">
          <p>{`Just this charge, or all ${t.merchant_charges} from ${t.merchant}?`}</p>
          <button type="button" className="btn" disabled={busy} onClick={() => merchantRule(asking)}>
            {`All ${t.merchant_charges}`}
          </button>
          <button type="button" className="btn ghost" disabled={busy} onClick={() => override(categoryBody(asking))}>Just this</button>
          <button type="button" className="btn ghost" disabled={busy} onClick={() => { setAsking(null); setFailed(null); }}>Cancel</button>
        </section>
      )}

      {showOffer && (
        <button type="button" className="btn ghost quiet" disabled={busy} onClick={() => merchantRule(offer)}>
          {`Use this for ${t.merchant} from now on`}
        </button>
      )}

      <section className="panel actions" aria-label="Change this charge">
        {t.kind !== "income" && (
          <button type="button" className="btn" disabled={busy} onClick={() => { setFailed(null); setPicking(true); }}>Change category</button>
        )}
        {spending && t.category !== FORGOTTEN && (
          <button type="button" className="btn ghost" disabled={busy} onClick={() => override({ category: FORGOTTEN })}>Can't remember</button>
        )}
        <button type="button" role="switch" aria-checked={t.one_off} className="btn ghost switch" disabled={busy}
          onClick={() => override({ one_off: !t.one_off })}>
          <span>One-off</span>
          <span className="small" aria-hidden="true">{t.one_off ? "On" : "Off"}</span>
        </button>
        {spending && (
          <button type="button" className="btn ghost" disabled={busy} onClick={() => override({ kind: "transfer" })}>Not spending</button>
        )}
        {t.kind === "income" && t.guessed && (
          <button type="button" className="btn ghost" disabled={busy} onClick={() => override({ kind: "income" })}>Yes, this is income</button>
        )}
        {t.kind === "income" && (
          <button type="button" className="btn ghost" disabled={busy} onClick={() => override({ kind: "transfer" })}>Not income</button>
        )}
        {t.why === "you set this" && (
          <button type="button" className="btn ghost" disabled={busy} onClick={undo}>Undo my change</button>
        )}
      </section>

      {picking && (
        <Sheet title="Change category" onClose={() => setPicking(false)}>
          <CategoryPicker value={t.category} onPick={chosen} />
        </Sheet>
      )}
    </div>
  );
}
