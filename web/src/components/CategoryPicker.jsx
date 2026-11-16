// The categories the server offers, folded into a few groups that open on a tap (the group holding the
// current category starts open), then a "New category" row for a name of
// his own. `value` is the current one (marked); `onPick(category)` is called with the chosen name, whether
// listed or typed. The server checks a typed name; if it refuses, the caller's save-failure message shows why.
import { useState } from "react";
import { get } from "../api.js";
import useLoad from "../useLoad.js";
import Loading from "./Loading.jsx";
import Problem from "./Problem.jsx";

// The picker's own grouping, for finding a category quickly. A category named here goes to its group;
// any other goes by its block (Food, or Bills and Subscriptions), and the rest to Other.
const GROUPS = ["Food", "Bills", "Shopping", "Fun", "Travel & transport", "Health", "Other"];
const NAMED = {
  Home: "Shopping", Clothes: "Shopping", Shopping: "Shopping", Gifts: "Shopping",
  Games: "Fun", Entertainment: "Fun", "Books & music": "Fun",
  Transport: "Travel & transport", Travel: "Travel & transport",
  Pharmacy: "Health", Therapy: "Health", "Eye care": "Health", "Medical & dental": "Health",
  "Personal care": "Health",
};
const BY_BLOCK = { Food: "Food", Bills: "Bills", Subscriptions: "Bills" };
const groupOf = (name, block) => NAMED[name] || BY_BLOCK[block] || "Other";

export default function CategoryPicker({ value, onPick }) {
  const { data, error, retry } = useLoad(() => get("categories"), []);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  if (error) return <Problem error={error} onRetry={retry} />;
  if (!data) return <Loading />;
  const trimmed = name.trim();
  return (
    <ul className="picker">
      {GROUPS.map((group) => {
        const names = data.categories.filter((n) => groupOf(n, data.blocks[n]) === group);
        if (!names.length) return null;
        return (
          <li key={group}>
            <details className="pick-group" open={names.includes(value)}>
              <summary><span>{group}</span><span className="small muted">{names.length}</span></summary>
              <ul className="picker">
                {names.map((n) => (
                  <li key={n}>
                    <button type="button" className="pick" aria-current={n === value ? "true" : undefined}
                      onClick={() => onPick(n)}>
                      <span>{n}{n === value && <span className="small muted"> (current)</span>}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          </li>
        );
      })}
      <li className="pick-new">
        {naming ? (
          <form className="new-category" onSubmit={(e) => { e.preventDefault(); if (trimmed) onPick(trimmed); }}>
            <label className="field">
              <span>Name</span>
              <input type="text" value={name} maxLength={40} autoCapitalize="sentences" autoFocus
                onChange={(e) => setName(e.target.value)} />
            </label>
            <div className="actions">
              <button type="submit" className="btn" disabled={!trimmed}>Use this</button>
              <button type="button" className="btn ghost" onClick={() => { setNaming(false); setName(""); }}>Cancel</button>
            </div>
          </form>
        ) : (
          <button type="button" className="pick" onClick={() => setNaming(true)}>New category</button>
        )}
      </li>
    </ul>
  );
}
