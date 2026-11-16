// The app's worker on the phone. Its one job is notifications: a reminder sent in the form the phone
// shows and opens by itself only needs us to report that it arrived. A phone that does not know that
// form gets the notification shown from here instead.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

function report(kind, id) {
  if (!id) return Promise.resolve();
  return fetch(new URL("api/v1/push/events", self.registration.scope), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-Budget-Client": "1" },
    body: JSON.stringify({ kind, id }),
  }).catch(() => {});
}

// The notification's id, wherever this phone put it.
function idOf(data, proposed) {
  const note = (data && data.notification) || {};
  const fromLink = /[?&]n=([0-9a-f]+)/.exec(note.navigate || (proposed && proposed.navigate) || "");
  return (note.data && note.data.id) || note.tag || (proposed && (proposed.tag || (proposed.data && proposed.data.id)))
    || (fromLink && fromLink[1]) || null;
}

self.addEventListener("push", (e) => {
  let data = null;
  try { data = e.data ? e.data.json() : null; } catch { data = null; }
  const id = idOf(data, e.notification);
  const note = (data && data.notification) || {};
  // e.notification is set when the phone is already showing it by itself
  if (e.notification || !note.title) { e.waitUntil(report("delivered", id)); return; }
  e.waitUntil(Promise.all([
    self.registration.showNotification(note.title, { body: note.body || "", tag: note.tag, data: { id, navigate: note.navigate } }),
    report("delivered", id),
  ]));
});

self.addEventListener("notificationclick", (e) => {
  const { id, navigate } = e.notification.data || {};
  e.notification.close();
  e.waitUntil(Promise.all([report("opened", id), self.clients.openWindow(navigate || self.registration.scope)]));
});
