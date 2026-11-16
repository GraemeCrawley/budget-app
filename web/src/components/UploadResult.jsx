// What an upload came to, in plain words. `UploadResult` shows the accepted batches (and lets an
// activity export be widened to the whole month); `UploadRefusal` shows a refusal and its question.
import { useState } from "react";
import { send } from "../api.js";
import { monthOnly, shortDate } from "../money.js";
import NewAccount from "./NewAccount.jsx";
import Problem from "./Problem.jsx";

const plural = (n, one, many) => (n === 1 ? `${n} ${one}` : `${n} ${many}`);

function lastDay(ym) {
  const [y, m] = ym.split("-").map(Number);
  return `${ym}-${String(new Date(Date.UTC(y, m, 0)).getUTCDate()).padStart(2, "0")}`;
}

function BatchResult({ batch, onChange }) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(null);
  const first = batch.period_start.slice(0, 7);
  const ym = batch.period_end.slice(0, 7);

  async function widen() {
    setBusy(true);
    setFailed(null);
    try {
      onChange(await send("PATCH", `batches/${batch.id}/period`, { period_start: `${first}-01`, period_end: lastDay(ym) }));
    } catch (e) {
      setFailed(e);
    } finally {
      setBusy(false);
    }
  }

  if (batch.status === "duplicate") {
    return <div className="panel"><p>This file was already uploaded</p></div>;
  }
  const refused = failed && failed.status === 422 && failed.detail;
  return (
    <div className="panel">
      <p><strong>{batch.kind === "statement"
        ? `${plural(batch.added, "charge", "charges")} on this statement for ${batch.account_name}, ${shortDate(batch.period_start)} to ${shortDate(batch.period_end)}`
        : `Added ${plural(batch.added, "charge", "charges")} for ${batch.account_name}, ${shortDate(batch.period_start)} to ${shortDate(batch.period_end)}`}</strong></p>
      {batch.already_held > 0 && <p className="small muted">{`${batch.already_held} were already here`}</p>}
      {batch.confirmed > 0 && <p className="small muted">{`Confirmed ${plural(batch.confirmed, "earlier charge", "earlier charges")}`}</p>}
      {batch.differences.length > 0 && (
        <details className="differences">
          <summary>{plural(batch.differences.length, "difference", "differences")}</summary>
          <ul className="plain small">{batch.differences.map((d) => <li key={d}>{d}</li>)}</ul>
        </details>
      )}
      {batch.message && <p className="note warn">{batch.message}</p>}
      {batch.can_widen && (
        <div className="stack">
          <p>{`This export covers ${shortDate(batch.period_start)} to ${shortDate(batch.period_end)}. Does it cover ${first === ym ? `all of ${monthOnly(ym)}` : `${monthOnly(first)} to ${monthOnly(ym)} in full`}?`}</p>
          {failed && (refused
            ? <Problem message={failed.detail} />
            : <Problem error={failed} message="Couldn't save that. Try again." onRetry={widen} retryLabel="Try again" />)}
          <button type="button" className="btn ghost" disabled={busy} onClick={widen}>Yes, the whole month</button>
        </div>
      )}
    </div>
  );
}

// `review` false leaves out the link to Review, for a screen that shows one link for several files.
export default function UploadResult({ batches: first, review = true }) {
  const [batches, setBatches] = useState(first);
  const taken = batches.filter((b) => b.status !== "duplicate");
  const latest = taken.map((b) => b.period_end.slice(0, 7)).sort().at(-1);
  return (
    <div className="stack" aria-label="Upload result" role="region">
      {batches.map((b, i) => (
        <BatchResult key={b.id} batch={b}
          onChange={(next) => setBatches(batches.map((x, j) => (j === i ? next : x)))} />
      ))}
      {review && latest && <a className="btn" href={`#/review/${latest}`}>{`Review ${monthOnly(latest)}`}</a>}
    </div>
  );
}

// `refusal` is the server's {code, reason, needs}. `resend(extra)` sends the same file again with
// `extra` fields added; `accounts` are the existing ones to choose from.
export function UploadRefusal({ refusal, accounts, disabled, resend, onCreated }) {
  const needs = refusal.needs || {};
  const owner = needs.file_is_for ? accounts.find((a) => a.name === needs.file_is_for) : null;
  return (
    <div className="panel" role="alert">
      {refusal.reason && <p>{refusal.reason}</p>}
      {needs.file_is_for && <p>{`This looks like a file for ${needs.file_is_for}.`}</p>}
      {owner && <button type="button" className="btn" disabled={disabled} onClick={() => resend({ account_key: owner.key })}>{`Send it to ${owner.name}`}</button>}
      {needs.choose_signs && (
        <div className="stack">
          <p>Are these charges shown as positive numbers?</p>
          <button type="button" className="btn" disabled={disabled} onClick={() => resend({ signs: "flip" })}>Yes, they're charges</button>
          <button type="button" className="btn ghost" disabled={disabled} onClick={() => resend({ signs: "as_is" })}>No, leave them</button>
        </div>
      )}
      {needs.choose_account && (
        <div className="stack" role="group" aria-label="Which account is it for?">
          <p>Which account is it for?</p>
          {accounts.map((a) => (
            <button key={a.key} type="button" className="btn ghost" disabled={disabled} onClick={() => resend({ account_key: a.key })}>{a.name}</button>
          ))}
          <NewAccount onCreated={onCreated} />
        </div>
      )}
    </div>
  );
}
