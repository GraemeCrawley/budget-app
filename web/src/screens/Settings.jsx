// Settings: how the app looks on this phone, and reminders.
import Reminders from "../components/Reminders.jsx";
import { versionWords } from "../version.js";

function Choice({ label, name, value, options, setPref }) {
  return (
    <section className="panel" role="group" aria-label={label}>
      <h2>{label}</h2>
      <div className="choices">
        {options.map(([v, words]) => (
          <button key={String(v)} type="button" aria-pressed={value === v} onClick={() => setPref(name, v)}>{words}</button>
        ))}
      </div>
    </section>
  );
}

export default function Settings({ prefs, setPref }) {
  return (
    <div className="screen">
      <h1>Settings</h1>
      <Choice label="Theme" name="theme" value={prefs.theme} setPref={setPref}
        options={[["dark", "Dark"], ["light", "Light"]]} />
      <Choice label="Text size" name="text" value={prefs.text} setPref={setPref}
        options={[["normal", "Normal"], ["large", "Large"], ["larger", "Larger"]]} />
      <Choice label="Amounts" name="hide" value={prefs.hide} setPref={setPref}
        options={[[false, "Shown"], [true, "Hidden"]]} />
      <Reminders />
      <section className="panel">
        <h2>Savings target and budgets</h2>
        <a className="btn ghost" href="#/plan">Open Plan</a>
      </section>
      <p className="small muted">Theme, text size and hidden amounts are kept on this phone only.</p>
      <p className="small muted">Version {versionWords()}</p>
    </div>
  );
}
