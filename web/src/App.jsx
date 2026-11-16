import { useEffect, useState } from "react";
import { get } from "./api.js";
import Nav from "./components/Nav.jsx";
import { useRoute } from "./router.js";
import Add from "./screens/Add.jsx";
import Block from "./screens/Block.jsx";
import Charge from "./screens/Charge.jsx";
import Home from "./screens/Home.jsx";
import Month from "./screens/Month.jsx";
import Months from "./screens/Months.jsx";
import Plan from "./screens/Plan.jsx";
import Review from "./screens/Review.jsx";
import Settings from "./screens/Settings.jsx";
import { usePrefs } from "./prefs.js";

// In report mode the server lets every request through as the owner, so say so quietly.
function useLoginCheck() {
  const [mode, setMode] = useState(null);
  useEffect(() => {
    get("me").then((me) => setMode(me.login_check), () => setMode(null));
  }, []);
  return mode;
}

export default function App() {
  const route = useRoute();
  const loginCheck = useLoginCheck();
  const [prefs, setPref] = usePrefs();
  // Keyed by the whole route so a screen remounts, and refetches, each time it is shown.
  const key = `${route.name}:${JSON.stringify(route.params)}`;
  let screen;
  if (route.name === "home") screen = <Home key={key} />;
  else if (route.name === "months") screen = <Months key={key} />;
  else if (route.name === "month") screen = <Month key={key} ym={route.params.ym} />;
  else if (route.name === "block") screen = <Block key={key} ym={route.params.ym} block={route.params.block} />;
  else if (route.name === "charge") screen = <Charge key={key} id={route.params.id} />;
  else if (route.name === "add") screen = <Add key={key} />;
  else if (route.name === "plan") screen = <Plan key={key} />;
  else if (route.name === "review") screen = <Review key={key} ym={route.params.ym} />;
  else if (route.name === "settings") screen = <Settings key={key} prefs={prefs} setPref={setPref} />;
  else screen = null;

  useEffect(() => {
    document.getElementById("root")?.scrollTo?.(0, 0); // #root is what scrolls, not the page
  }, [key]);

  return (
    <>
      <main className="app">
        <div className="topbar">
          <button type="button" aria-pressed={prefs.hide} onClick={() => setPref("hide", !prefs.hide)}>
            {prefs.hide ? "Show amounts" : "Hide amounts"}
          </button>
          <a href="#/settings" aria-current={route.name === "settings" ? "page" : undefined}>Settings</a>
        </div>
        {loginCheck === "report" && <p className="small muted">The login check is in report mode.</p>}
        {screen}
      </main>
      <Nav route={route.name} />
    </>
  );
}
