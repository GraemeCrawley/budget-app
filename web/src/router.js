// Hash routes, so the client works under any path prefix with no server routing.
import { useEffect, useState } from "react";

const YM = /^\d{4}-(0[1-9]|1[0-2])$/;
const HOME = { name: "home", params: {} };

export function parse(hash) {
  let parts;
  try {
    parts = (hash || "").replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  } catch {
    return HOME; // a malformed escape
  }
  const [head, a, b] = parts;
  if (parts.length === 0) return HOME;
  if (head === "months" && parts.length === 1) return { name: "months", params: {} };
  if (head === "month" && parts.length === 2 && YM.test(a)) return { name: "month", params: { ym: a } };
  if (head === "block" && parts.length === 3 && YM.test(a)) return { name: "block", params: { ym: a, block: b } };
  if (head === "charge" && parts.length === 2) return { name: "charge", params: { id: a } };
  if (head === "add" && parts.length === 1) return { name: "add", params: {} };
  if (head === "review" && parts.length === 1) return { name: "review", params: {} }; // every month at once
  if (head === "plan" && parts.length === 1) return { name: "plan", params: {} };
  if (head === "settings" && parts.length === 1) return { name: "settings", params: {} };
  if (head === "review" && parts.length === 2 && YM.test(a)) return { name: "review", params: { ym: a } };
  return HOME;
}

// go("#/add") and go("/add") both land on #/add.
export function go(path) {
  location.hash = path.replace(/^#?\/?/, "/");
}

export function useRoute() {
  const [route, setRoute] = useState(() => parse(location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parse(location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
