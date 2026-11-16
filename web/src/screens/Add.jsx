// Add: one card per account, each with its own file input, plus one for files that name their own
// account. Several files can be chosen at once; they are sent one at a time, and each chosen File
// stays in its item so it can be sent again once a question is answered.
import { useEffect, useRef, useState } from "react";
import { get, upload } from "../api.js";
import { missingMonths, missingSpans, waitingAfter, wholeMonths } from "../missing.js";
import { monthName, monthOnly, shortDate } from "../money.js";
import AccountCard from "../components/AccountCard.jsx";
import Loading from "../components/Loading.jsx";
import NewAccount from "../components/NewAccount.jsx";
import Problem, { signInExpired } from "../components/Problem.jsx";
import UploadResult, { UploadRefusal } from "../components/UploadResult.jsx";
import useLoad from "../useLoad.js";

const isRefusal = (e) => !signInExpired(e) && e.body && e.body.reason;
// What an account lacks, in words: whole months by name ("August, September"), anything else by its days.
function inWords(spans) {
  return spans.map((s) => {
    const months = wholeMonths(s);
    if (months) return months.map(monthOnly).join(", ");
    return s[0] === s[1] ? shortDate(s[0]) : `${shortDate(s[0])} to ${shortDate(s[1])}`;
  }).join(", ");
}
const plural = (n) => (n === 1 ? "1 file" : `${n} files`);

export default function Add() {
  const { data, error, retry } = useLoad(() => get("accounts"), []);
  const [list, setList] = useState(null); // the accounts as last changed here; wins over the first load
  // One item per chosen file: {id, name, file, account_key, signs, state, batches | refusal | error}.
  // state is waiting, sending, done, refused or failed. The File is dropped once it is in.
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(null); // the error when the accounts could not be fetched again

  const outcomeRef = useRef(null);
  const sending = useRef(false);
  const held = useRef([]); // the items as the sending loop sees them, ahead of the next render
  const nextId = useRef(1);

  // The outcome appears above the cards, and the owner tapped one lower down: bring it into view.
  useEffect(() => {
    if ((busy || held.current.length) && outcomeRef.current) {
      outcomeRef.current.scrollIntoView?.({ block: "start", behavior: "smooth" });
      outcomeRef.current.focus({ preventScroll: true });
    }
  }, [busy]);

  if (error) return <Problem error={error} onRetry={retry} />;
  if (!data) return <Loading />;
  const accounts = list ?? data.accounts;

  async function refresh() {
    try {
      setList((await get("accounts")).accounts);
      setStale(null);
    } catch (e) {
      setStale(e);
    }
  }

  function put(next) {
    held.current = next;
    setItems(next);
  }
  const patch = (id, change) => put(held.current.map((i) => (i.id === id ? { ...i, ...change } : i)));

  // Sends each waiting file in turn. A refused file is set aside with its question and the rest go
  // on; a file that could not be sent at all stops the run, since the next would fail the same way.
  async function run() {
    if (sending.current) return; // a double tap sends once
    sending.current = true;
    setBusy(true);
    let added = false;
    try {
      for (;;) {
        const item = held.current.find((i) => i.state === "waiting");
        if (!item) break;
        patch(item.id, { state: "sending" });
        const form = new FormData();
        form.append("file", item.file);
        if (item.account_key) form.append("account_key", item.account_key);
        if (item.signs) form.append("signs", item.signs);
        try {
          const res = await upload("uploads", form);
          patch(item.id, { state: "done", batches: res.batches, file: null }); // nothing about the file is kept
          added = true;
        } catch (e) {
          // a 401's body carries a reason code too; only a refusal of the file is shown as one
          if (isRefusal(e)) {
            patch(item.id, { state: "refused", refusal: e.body });
          } else {
            patch(item.id, { state: "failed", error: e });
            break;
          }
        }
      }
    } finally {
      sending.current = false;
      setBusy(false);
      if (added) refresh();
    }
  }

  function start(files, account_key) {
    if (sending.current || !files.length) return;
    put(files.map((file) => ({ id: nextId.current++, name: file.name, file, account_key, state: "waiting" })));
    run();
  }

  // The same file again, with an answer added (or as it was, after a failure); then any still waiting.
  function resend(id, extra = {}) {
    if (sending.current) return;
    patch(id, { ...extra, state: "waiting", refusal: null, error: null });
    run();
  }

  const created = (account) => setList([...accounts, account]);
  const changed = (account) => setList(accounts.map((a) => (a.key === account.key ? account : a)));

  // One card per institution that holds several accounts; every other account has its own card.
  const cards = [];
  for (const a of accounts) {
    const card = a.institution && cards.find((c) => c.institution === a.institution);
    if (card) card.accounts.push(a);
    else cards.push({ institution: a.institution, accounts: [a] });
  }
  // Each card's title is its source: the institution, or the lone account's own name.
  const today = new Date().toLocaleDateString("en-CA");
  for (const card of cards) {
    card.title = card.accounts.length > 1 ? card.institution : card.accounts[0].name;
    card.missing = card.accounts.map((acc) => ({ name: acc.name, lacks: inWords(missingSpans(acc.ranges, today)) }))
      .filter((m) => m.lacks);
    card.waiting = card.accounts.map((acc) => ({ name: acc.name, after: waitingAfter(acc.ranges, today) }))
      .filter((w) => w.after);
  }
  // By month, the sources with a gap in it; the detail is on each source's own card.
  const missing = missingMonths(
    cards.flatMap((card) => card.accounts.map((acc) => ({ name: card.title, ranges: acc.ranges }))), today)
    .map((m) => ({ month: m.month, sources: [...new Set(m.accounts.map((acc) => acc.name))] }));
  const many = items.length > 1;
  const done = items.filter((i) => i.state === "done");
  const at = items.findIndex((i) => i.state === "sending");
  const latest = done.flatMap((i) => i.batches).filter((b) => b.status !== "duplicate")
    .map((b) => b.period_end.slice(0, 7)).sort().at(-1);
  const pick = (account_key) => (e) => {
    const files = [...e.target.files];
    e.target.value = "";
    start(files, account_key);
  };

  return (
    <div className="screen">
      <h1>Add files</h1>
      <section className="panel">
        <label className={`btn file${busy ? " disabled" : ""}`}>
          Add files
          <input type="file" multiple accept=".csv,.pdf,.txt" aria-label="Add files for any account" disabled={busy}
            onChange={pick(undefined)} />
        </label>
        {import.meta.env.VITE_MOCK && (
          <p className="note" role="note">Demo: your file stays on your phone and its contents are not read.</p>
        )}
        <p className="small muted">Pick everything you downloaded, from any bank, all at once. Each file finds its
          own account, and a new account is made the first time its file arrives.</p>
        <NewAccount onCreated={created} />
      </section>

      <div className="outcome" ref={outcomeRef} tabIndex={-1} aria-live="polite" data-testid="outcome">
        {many && (
          <p className="small muted">
            {at >= 0 ? `Adding file ${at + 1} of ${items.length}` : `${done.length} of ${plural(items.length)} added`}
          </p>
        )}
        {items.map((item) => (
          <div key={item.id} className="stack" role={many ? "group" : undefined} aria-label={many ? item.name : undefined}>
            {many && <h2 className="filename">{item.name}</h2>}
            {item.state === "sending" && <Loading />}
            {item.state === "waiting" && many && <p className="small muted">{busy ? "Waiting" : "Not sent yet"}</p>}
            {item.state === "failed" && (
              <Problem error={item.error} message="Couldn't add that file. Try again." onRetry={() => resend(item.id)} retryLabel="Try again" />
            )}
            {item.state === "refused" && (
              <UploadRefusal refusal={item.refusal} accounts={accounts} disabled={busy}
                // An account made to answer "which account is it for?" is the answer: send the file to it.
                onCreated={(account) => { created(account); resend(item.id, { account_key: account.key }); }}
                resend={(extra) => resend(item.id, extra)} />
            )}
            {item.state === "done" && <UploadResult batches={item.batches} review={!many} />}
          </div>
        ))}
        {many && latest && <a className="btn" href={`#/review/${latest}`}>{`Review ${monthOnly(latest)}`}</a>}
      </div>
      {stale && <Problem error={stale} message="Couldn't refresh the dates below. Try again." onRetry={refresh} retryLabel="Try again" />}

      <section className="panel" aria-label="Still missing">
        <h2>Still missing</h2>
        {missing.length === 0
          ? <p className="small muted">Nothing. Every account covers every finished month.</p>
          : (
            <ul className="plain missing">
              {missing.map((m) => (
                <li key={m.month}>
                  <strong>{monthName(m.month)}</strong>
                  <span className="small muted">{m.sources.join(", ")}</span>
                </li>
              ))}
            </ul>
          )}
      </section>

      <h2>Accounts so far</h2>
      {cards.map((card) => (
        <AccountCard key={card.accounts[0].key} accounts={card.accounts} institution={card.institution}
          missing={card.missing} waiting={card.waiting}
          disabled={busy} onChanged={changed}
          // an institution's files each name their own account; a lone account's files are sent to it
          onFiles={(files) => start(files, card.accounts.length > 1 ? undefined : card.accounts[0].key)} />
      ))}
    </div>
  );
}
