// The bottom bar, with the version under it on every screen.
import { versionWords } from "../version.js";

const HOME = { label: "Home", href: "#/", names: ["home"] };
const MONTHS = { label: "Months", href: "#/months", names: ["months", "month", "block", "charge", "charges"] };
const PLAN = { label: "Plan", href: "#/plan", names: ["plan"] };
const ADD = { label: "Add", href: "#/add", names: ["add"] };

function Item({ item, route }) {
  return <a href={item.href} aria-current={item.names.includes(route) ? "page" : undefined}>{item.label}</a>;
}

export default function Nav({ route }) {
  return (
    <>
      <nav className="nav" aria-label="Main">
        <Item item={HOME} route={route} />
        <Item item={MONTHS} route={route} />
        <Item item={PLAN} route={route} />
        <Item item={ADD} route={route} />
      </nav>
      <p className="navfoot">Version {versionWords()}</p>
    </>
  );
}
