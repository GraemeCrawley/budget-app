// One merchant group waiting for a category: its name, count and total, a way to choose, and a way
// to see its charges. A group with no merchant shows its charges at once, each to be set by itself.
import { useState } from "react";
import { exact } from "../money.js";
import ChargeRow from "./ChargeRow.jsx";

export default function PlaceGroup({ group, disabled, onChoose, onForget, onOpen }) {
  const [open, setOpen] = useState(false);
  const named = Boolean(group.merchant);
  const label = named ? group.merchant : "No merchant";
  return (
    <li className="group" data-testid="group">
      <div className="row group-head">
        <div>
          <strong>{label}</strong>
          <p className="small muted amt">{`${group.count} ${group.count === 1 ? "charge" : "charges"}, ${exact(group.cents)}`}</p>
        </div>
      </div>
      {named && (
        <div className="group-actions">
          <button type="button" className="btn" disabled={disabled} onClick={() => onChoose(group.charges[0], group)}
            aria-label={`Choose a category for ${group.merchant}`}>Choose category</button>
          <button type="button" className="btn ghost" aria-expanded={open} aria-label={`Show the charges from ${group.merchant}`}
            onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</button>
          <button type="button" className="btn ghost wide" disabled={disabled} onClick={() => onForget(group.charges)}
            aria-label={`Can't remember what ${group.merchant} was`}>Can't remember</button>
        </div>
      )}
      {(open || !named) && (
        <ul className="plain">
          {group.charges.map((c) => (
            <li key={c.id} className={named ? undefined : "unnamed"}>
              <ChargeRow charge={c} detail onOpen={() => onOpen(c)} />
              {!named && (
                <div className="group-actions">
                  <button type="button" className="btn ghost" disabled={disabled} onClick={() => onChoose(c, null)}
                    aria-label={`Choose a category for ${c.description}`}>Choose category</button>
                  <button type="button" className="btn ghost" disabled={disabled} onClick={() => onForget([c])}
                    aria-label={`Can't remember what ${c.description} was`}>Can't remember</button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
