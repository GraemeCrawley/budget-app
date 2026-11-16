// One charge in a list: date, merchant (or the bank's description), category and account, amount.
// `onOpen(charge)` is called when it is tapped. A charge not yet on a statement carries a small
// "unconfirmed" mark. With `detail` the row also shows what the bank called the charge, and where
// and when it happened, so a charge can be recognised; the whole row is still one tap target.
import { exact, longDate, shortDate } from "../money.js";

const KIND_WORDS = { income: "Income", transfer: "Not counted", saving: "Saved" };

export default function ChargeRow({ charge, onOpen, detail = false }) {
  const label = charge.category || KIND_WORDS[charge.kind] || charge.kind;
  const heading = charge.merchant || charge.description;
  const where = [charge.account_name, longDate(charge.date)];
  if (charge.provisional) where.push("not yet confirmed by a statement");
  if (charge.one_off) where.push("one-off");
  return (
    <button type="button" className={detail ? "charge-row detailed" : "charge-row"} onClick={() => onOpen(charge)}>
      <span className="small muted date">{shortDate(charge.date)}</span>
      <span className="what">
        <strong>{heading}</strong>
        <span className="small muted">
          {detail || !charge.account_name ? label : `${label} · ${charge.account_name}`}
          {charge.provisional && <span className="mark"> unconfirmed</span>}
          {charge.first_time && <span className="mark"> new</span>}
        </span>
        {detail && charge.description && charge.description !== heading && (
          <span className="small muted raw">{charge.description}</span>
        )}
        {detail && <span className="small muted">{where.join(" · ")}</span>}
      </span>
      <span className="num">{exact(charge.amount_cents)}</span>
    </button>
  );
}
