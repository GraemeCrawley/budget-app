// "New account": a name and a kind. `onCreated(account)` gets what the server returned. A failed
// create keeps what was typed, and "Try again" sends the same thing.
import { useState } from "react";
import { send } from "../api.js";
import Problem from "./Problem.jsx";

const KINDS = ["chequing", "card", "savings", "investment"];

export default function NewAccount({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("chequing");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(null);

  async function create() {
    setBusy(true);
    setFailed(null);
    try {
      const account = await send("POST", "accounts", { name: name.trim(), kind });
      setOpen(false);
      setName("");
      onCreated(account);
    } catch (e) {
      setFailed(e);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return <button type="button" className="btn ghost" onClick={() => setOpen(true)}>New account</button>;
  }
  // A refusal the owner can act on (a name already used, a blank name) is shown as the server says it.
  const plain = failed && (failed.status === 409 || failed.status === 422) && failed.detail;
  return (
    <form className="panel" onSubmit={(e) => { e.preventDefault(); if (name.trim()) create(); }}>
      <label className="field">
        <span>Name</span>
        <input value={name} onChange={(e) => { setName(e.target.value); if (plain) setFailed(null); }} disabled={busy} autoComplete="off" />
      </label>
      <label className="field">
        <span>Kind</span>
        <select value={kind} onChange={(e) => setKind(e.target.value)} disabled={busy}>
          {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
      </label>
      {failed && (plain
        ? <Problem message={failed.detail} />
        : <Problem error={failed} message="Couldn't save that. Try again." onRetry={create} retryLabel="Try again" />)}
      <button type="submit" className="btn" disabled={busy || !name.trim()}>Create account</button>
      <button type="button" className="btn ghost" disabled={busy} onClick={() => { setOpen(false); setFailed(null); }}>Cancel</button>
    </form>
  );
}
