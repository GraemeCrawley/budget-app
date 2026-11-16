// How the app looks on this phone: theme, text size, and whether amounts are hidden. Kept in the
// browser, since these are choices about one screen, not about the money. Storage can be missing or
// blocked; then the choices last until the app is closed.
import { useEffect, useState } from "react";

const KEY = "budget.prefs";
export const DEFAULTS = { theme: "dark", text: "normal", hide: false };
const ALLOWED = { theme: ["dark", "light"], text: ["normal", "large", "larger"], hide: [true, false] };

export function clean(raw) {
  const out = { ...DEFAULTS };
  for (const k of Object.keys(DEFAULTS)) {
    if (raw && ALLOWED[k].includes(raw[k])) out[k] = raw[k];
  }
  return out;
}

export function load() {
  try {
    return clean(JSON.parse(localStorage.getItem(KEY)));
  } catch {
    return { ...DEFAULTS };
  }
}

function save(prefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    // nothing to do: the choice still holds for this visit
  }
}

// The stylesheet reads these from the root element.
export function apply(prefs, root = document.documentElement) {
  root.dataset.theme = prefs.theme;
  if (prefs.text === "normal") delete root.dataset.text;
  else root.dataset.text = prefs.text;
  if (prefs.hide) root.dataset.hide = "";
  else delete root.dataset.hide;
}

export function usePrefs() {
  const [prefs, setPrefs] = useState(load);
  useEffect(() => apply(prefs), [prefs]);
  const setPref = (name, value) => setPrefs((old) => {
    const next = clean({ ...old, [name]: value });
    save(next);
    return next;
  });
  return [prefs, setPref];
}
