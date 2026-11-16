// Reminders on this phone: the app's own notifications. On an iPhone they only work once the app has
// been added to the home screen and opened from there.
import { get, send } from "./api.js";

const mock = Boolean(import.meta.env.VITE_MOCK);

// "ok", "home-screen" (an iPhone browser tab: add the app to the home screen first) or "no".
export function support() {
  if (mock) return "ok";
  if ("serviceWorker" in navigator && "PushManager" in window && "Notification" in window) return "ok";
  const iPhone = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const standalone = navigator.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches;
  return iPhone && !standalone ? "home-screen" : "no";
}

function bytes(key) {
  const padded = (key + "===".slice((key.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

// Start the worker so the phone can report that a reminder arrived. Safe to call on every open.
export function startWorker() {
  if (mock || support() !== "ok") return Promise.resolve(null);
  return navigator.serviceWorker.register("./sw.js").catch(() => null);
}

async function mine() {
  if (mock) return globalThis.__mockPhone || null;
  const worker = await navigator.serviceWorker.getRegistration();
  return worker ? worker.pushManager.getSubscription() : null;
}

// { on: this phone has reminders, phones: how many do, last: the last notification sent }
export async function state() {
  const [server, sub] = await Promise.all([get("push"), support() === "ok" ? mine() : null]);
  return { on: Boolean(sub), phones: server.phones, last: server.last };
}

export async function turnOn() {
  if (mock) {
    globalThis.__mockPhone = { endpoint: "mock" };
    await send("POST", "push/subscriptions", { endpoint: "mock", keys: { p256dh: "k", auth: "a" } });
    return;
  }
  const allowed = await Notification.requestPermission();
  if (allowed !== "granted") throw new Error("Notifications are turned off for this app in the phone's settings.");
  await navigator.serviceWorker.register("./sw.js");
  const [worker, { key }] = await Promise.all([navigator.serviceWorker.ready, get("push")]);
  const sub = await worker.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes(key) });
  const { endpoint, keys } = sub.toJSON();
  await send("POST", "push/subscriptions", { endpoint, keys });
}

export async function turnOff() {
  const sub = await mine();
  if (!sub) return;
  await send("DELETE", "push/subscriptions", { endpoint: sub.endpoint });
  if (mock) globalThis.__mockPhone = null;
  else await sub.unsubscribe();
}

export function sendTest() {
  return send("POST", "push/test");
}

// A reminder opens the app at an address carrying its id (?n=...). Tell the server it was opened,
// then drop the id from the address so a reload does not report it again.
export function reportOpened() {
  const id = new URLSearchParams(window.location.search).get("n");
  if (!id) return;
  window.history.replaceState(null, "", window.location.pathname + window.location.hash);
  send("POST", "push/events", { id, kind: "opened" }).catch(() => {});
}
