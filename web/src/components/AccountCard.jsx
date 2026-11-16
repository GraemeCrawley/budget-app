// One card on the Add screen: a single account, or every account held at one institution. It shows
// how far the data goes, the owner's own note on how to export (folded away until opened; for an institution the
// one note is saved on each of its accounts), and a file input.
import { useState } from "react";
import { send } from "../api.js";
import { shortDate } from "../money.js";
import Problem from "./Problem.jsx";

const through = (a) => (a.data_through ? `Data through ${shortDate(a.data_through)}` : "Nothing yet");

// `accounts` has one account, or several that share `institution`. `onFiles(files)` gets the chosen files.
// `missing` is [{name, lacks}]: what each account still lacks, in words; empty when nothing is.
// `waiting` is [{name, after}]: accounts whose next file is not out yet, and the day their data ends.
export default function AccountCard({ accounts, institution, missing = [], waiting = [], disabled, onFiles, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(null);
  const grouped = accounts.length > 1;
  const title = grouped ? institution : accounts[0].name;
  const note = accounts.map((a) => a.export_note).find(Boolean) ?? "";

  const startEdit = () => { setDraft(note); setEditing(true); };

  async function save() {
    setBusy(true);
    setFailed(null);
    try {
      const saved = await Promise.all(accounts.map((a) => send("PATCH", `accounts/${a.key}`, { export_note: draft })));
      saved.forEach(onChanged);
      setEditing(false);
    } catch (e) {
      setFailed(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-label={title}>
      <div className="row">
        <h2>{title}</h2>
        {!grouped && <span className="small muted">{through(accounts[0])}</span>}
      </div>
      {grouped && (
        <ul className="plain held">
          {accounts.map((a) => (
            <li key={a.key} className="row"><span>{a.name}</span><span className="small muted">{through(a)}</span></li>
          ))}
        </ul>
      )}
      {missing.length > 0 && (
        <div className="note warn" role="group" aria-label={`Missing for ${title}`}>
          <strong>Missing</strong>
          <ul className="plain">
            {missing.map((m) => <li key={m.name}>{grouped ? `${m.name}: ${m.lacks}` : m.lacks}</li>)}
          </ul>
        </div>
      )}
      {waiting.map((w) => (
        <p key={w.name} className="small muted">
          {`${grouped ? `${w.name}: nothing` : "Nothing"} to fetch yet. Charges after ${shortDate(w.after)} come with the next statement.`}
        </p>
      ))}
      {editing ? (
        <div className="stack">
          <label className="field">
            <span className="small muted">{grouped ? "How you export these" : "How you export this one"}</span>
            <textarea rows={3} value={draft} disabled={busy} onChange={(e) => setDraft(e.target.value)} />
          </label>
          {failed && <Problem error={failed} message="Couldn't save that. Try again." onRetry={save} retryLabel="Try again" />}
          <button type="button" className="btn" disabled={busy} onClick={save}>Save note</button>
          <button type="button" className="btn ghost" disabled={busy}
            onClick={() => { setEditing(false); setFailed(null); }}>Cancel</button>
        </div>
      ) : (
        note ? (
          // the steps stay folded away until wanted, so the cards are short enough to scan
          <details className="guide">
            <summary>How to export</summary>
            <p className="guide-text">{note}</p>
            <button type="button" className="link" onClick={startEdit}>Edit note</button>
          </details>
        ) : (
          <button type="button" className="note-btn" onClick={startEdit}>
            <span className="muted">{grouped ? "Add a note on how you export these" : "Add a note on how you export this one"}</span>
          </button>
        )
      )}
      <label className={`btn ghost file${disabled ? " disabled" : ""}`}>
        {grouped ? `Add ${institution} files` : "Add files to this account only"}
        <input type="file" multiple accept=".csv,.pdf,.txt" aria-label={`Add files for ${title}`} disabled={disabled}
          onChange={(e) => { const files = [...e.target.files]; e.target.value = ""; if (files.length) onFiles(files); }} />
      </label>
    </section>
  );
}
