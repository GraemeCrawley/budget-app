// Reminders on this phone: turn the app's own notifications on or off, and send one to try it.
import { useEffect, useState } from "react";
import { sendTest, state as readState, support, turnOff, turnOn } from "../push.js";
import { shortDate } from "../money.js";

// "2026-11-16T07:00:03-05:00" -> "Nov 16, 07:00"
const when = (iso) => `${shortDate(iso)}, ${iso.slice(11, 16)}`;

function lastWords(last) {
  if (!last) return "No reminder has been sent yet.";
  const what = last.kind === "test" ? "Last test" : "Last reminder";
  const then = last.opened_at ? `opened ${when(last.opened_at)}`
    : last.delivered_at ? "arrived, not opened from the notification" : "not opened from the notification";
  return `${what} sent ${when(last.sent_at)}: ${then}.`;
}

export default function Reminders() {
  const can = support();
  const [now, setNow] = useState(null); // { on, phones, last }
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState("");

  const read = () => readState().then(setNow).catch(() => setSaid("Could not check reminders."));
  useEffect(() => { read(); }, []);

  const act = async (work, done) => {
    setBusy(true);
    setSaid("");
    try {
      await work();
      setSaid(done);
    } catch (e) {
      setSaid(e?.detail || e?.message || "That did not work.");
    }
    await read();
    setBusy(false);
  };

  return (
    <section className="panel" role="region" aria-label="Reminders">
      <h2>Reminders</h2>
      <p>On the 1st of the month this phone is reminded to add last month's files, naming the accounts still needed. It stops when they are in.</p>
      {can === "home-screen" && <p className="small muted">On an iPhone, add this app to the home screen (Share, then Add to Home Screen) and open it from there to turn reminders on.</p>}
      {can === "no" && <p className="small muted">This browser cannot show notifications.</p>}
      {can === "ok" && now && (now.on ? (
        <>
          <p className="small muted">Reminders are on for this phone.</p>
          <button type="button" className="btn" disabled={busy}
            onClick={() => act(sendTest, "Sent. It should appear in a few seconds; tap it to check it opens the app.")}>Send a test reminder</button>
          <button type="button" className="btn ghost" disabled={busy}
            onClick={() => act(turnOff, "Reminders are off for this phone.")}>Turn reminders off</button>
        </>
      ) : (
        <button type="button" className="btn" disabled={busy}
          onClick={() => act(turnOn, "Reminders are on for this phone.")}>Turn on reminders on this phone</button>
      ))}
      {said && <p className="small" role="status">{said}</p>}
      {now && <p className="small muted">{lastWords(now.last)}</p>}
      {now && !now.on && now.phones > 0 && <p className="small muted">Another device already gets them.</p>}
    </section>
  );
}
