# Phone notifications from a home-screen web app: playbook

Notes for any self-hosted web app that wants its
own phone notifications. It records what was tested on an iPhone, what
was built from those tests, and what is still unproven, so the tests do not have to be repeated.

"Web Push" here means the browser standard for sending a notification to a phone through the phone
maker's push service. "Service worker" means the small script a web app installs on the phone that
can run when the app is closed. "VAPID" is the signing key pair that identifies the sender to the
push service.

## 1. What was tested, and the result

Tested 2026-11-12 on an iPhone, system version 18.7, with the app added to the home screen
behind Cloudflare Access. The throwaway test code is not kept; the build described below replaced it.

| Question | Result |
|---|---|
| Does the Cloudflare Access login work inside the home-screen app? | Yes. The service worker's own requests carry the login cookie when sent with `credentials: "include"`. |
| Do notifications arrive? | Yes, in both forms below. |
| Classic form (service worker shows the notification, and handles the tap in `notificationclick`) | Arrives. **The tap event did not fire in any of 7 attempts.** This is a long-standing iPhone problem. Never depend on `notificationclick` on an iPhone. |
| Declarative form (iPhone system 18.4 and later: the message itself says what to show and which address to open, and the phone does both with no app code) | Arrived and opened the address on tap, 2 of 2. The opened page logged the tap within a few seconds. |
| Can delivery be logged? | Yes: the service worker's `push` event ran in both forms and reported back. |
| Did the notification's id reach the service worker in the declarative form? | **No**, not where the test put it (`notification.data.id`). The production worker now looks in several places (section 4). |
| Does a browser tab (not home screen) work on an iPhone? | No. Push only exists once the app is added to the home screen and opened from there. |

**Proven with the production build** (2026-11-16, same iPhone, declarative form, sent from the app's
Settings screen):
- Turning reminders on from the home-screen app, then "Send a test": the notification arrived.
- "Arrived" was recorded: the production service worker found the notification's id in the
  declarative message and reported it (2 of 2 tests).
- "Opened" was recorded from the opened page when the notification was tapped (1 of 1 tapped; the
  second test was left untapped and correctly shows as arrived, not opened).

**Not yet proven:**
- A scheduled reminder sent while the app is closed and the phone has been idle for days (the
  tests above were sent while the app was in use).
- Whether removing and re-adding the home-screen icon drops the phone's subscription. Assume it
  does, and have the app show whether this phone is subscribed.
- Android and desktop browsers. The code allows their push services but none was tested.

## 2. Rules the build follows because of those results

1. **Send the declarative form.** The message body is JSON:
   `{"web_push": 8030, "mutable": true, "notification": {"title", "body", "navigate", "tag", "data"}}`.
   `8030` is the fixed marker for this form. `navigate` is the full address the phone opens on a tap.
   `mutable: true` still wakes the service worker so it can report arrival.
2. **Log the tap from the opened page, not from the worker.** Put the notification's id in the
   address (`https://site/app/?n=<id>#/route`). On start-up the page reads `n`, reports "opened",
   then removes `n` from the address with `history.replaceState` so a reload does not report twice.
   With hash routing the query goes before the `#`.
3. **Keep a fallback in the worker** for phones that do not know the declarative form: if the push
   event has no `event.notification` (the phone is not already showing it), call `showNotification`.
4. **Ask for permission only from a tap.** `Notification.requestPermission()` must be called inside
   a button's click handler, and on an iPhone only from the home-screen app.
5. **Tell the user what to do when it cannot work.** In an iPhone browser tab, say "add this app to
   the home screen and open it from there" and show no button.
6. **A tap that is seen but not tapped cannot be detected.** Record it as unknown, not as ignored.

## 3. Server side (Python, FastAPI, SQLite)

Code: `tracker/push.py` (all logic), the `/push` routes at the end of `tracker/api.py`,
`tracker/schema_v4.sql` (two tables), the `remind` command in `tracker/cli.py`. Tests:
`tests/tracker/test_push.py`. Dependency: `pywebpush==2.0.0` (brings `cryptography`), Python 3.11.

- **Signing key:** generated on first use (`ec.SECP256R1`), written PEM to the app's private data
  directory with mode 0600 using `O_EXCL`, never in the image or the repo. The public half is sent
  to the phone as unpadded URL-safe base64 of the uncompressed point.
- **VAPID contact ("sub"):** the site's origin (`https://host`), never an email address, so no
  personal detail goes to the push service.
- **`pywebpush.webpush(...)` changes the `vapid_claims` dict it is given** (adds audience and
  expiry). Pass a fresh dict on every call or the second send to a different service fails.
- **Send options:** `ttl=86400`, header `Urgency: high`, `timeout=20`.
- **Only accept addresses at known push services** (`web.push.apple.com`, `*.push.apple.com`,
  `fcm.googleapis.com`, `updates.push.services.mozilla.com`, `*.notify.windows.com`, https only).
  Otherwise a subscription is a way to make the server send requests anywhere.
- **Drop a phone when the push service answers 404 or 410** (it no longer knows the phone). Keep it
  on any other failure.
- **Routes** (all behind the app's login; writes need the app's own request header):
  `GET push` (public key, number of phones, last notification), `POST push/subscriptions`,
  `DELETE push/subscriptions`, `POST push/test`, `POST push/events` (`delivered` or `opened`).
- **Record per notification:** id, kind, sent time, how many phones accepted it, first arrival
  time, first opened time. First report wins; repeats are ignored.
- **Text rule:** no dollar figures and nothing sensitive in the title or body; they show on a
  locked screen and pass through the phone maker's servers.
- **Make the network call replaceable** (`deliver=` argument, module-level `_deliver`) so tests
  never touch the network.

## 4. Phone side

Code: `web/public/sw.js` (service worker), `web/src/push.js` (subscribe, unsubscribe, test, report
opened), `web/src/components/Reminders.jsx` (the Settings panel), two lines in `web/src/main.jsx`.
Tests: `web/src/components/Reminders.test.jsx`.

- **Serving under a path prefix** (`/budget/`): register with a relative address
  (`navigator.serviceWorker.register("./sw.js")`), keep `sw.js` at the app's root so its scope is
  the whole app, and build addresses in the worker from `self.registration.scope`.
- **`sw.js` must not be cached for long.** Serve it and the page with `Cache-Control: no-cache`;
  only content-hashed files get a long lifetime. (Phones kept an old build for days before this.)
- **Worker requests need `credentials: "include"`** and whatever header the app requires on writes.
- **Finding the id in the worker:** check `data.notification.data.id`, `data.notification.tag`,
  `event.notification.tag`, `event.notification.data.id`, then the `n=` in the `navigate` address.
- **Subscribe:** `pushManager.subscribe({userVisibleOnly: true, applicationServerKey: <bytes>})`,
  then post `subscription.toJSON()` (`endpoint`, `keys.p256dh`, `keys.auth`) to the server.
- **Manifest:** `display: standalone`, `start_url` and `scope` relative (`./`), plus
  `apple-mobile-web-app-capable` and an `apple-touch-icon` in the page head.
- **An iPhone keeps the old icon** on an existing home-screen shortcut; the user must remove and
  re-add it to see a new one.

## 5. Scheduling

- A host timer (cron) runs the app's own command inside the
  container: `docker exec <app> python -m tracker.cli remind`.
- The command decides whether anything is due. Exit 0: sent, or nothing was due. Exit 3: due, but
  no phone could be reached. It prints one line with no figures and no names.
- **This app has no second channel.** If no phone is subscribed, nobody is reminded; exit 3 makes
  that visible in the cron log and to any job monitoring. An app that keeps a backup channel
  should keep its secrets on the host, never in the container, and fall back on one run only so
  follow-ups do not become repeated messages.
- Timer lines used: `0 7,10,12 1,4,7,10 * *`.
- **Gotcha:** a schema change needs the app to upgrade the database at start-up before any
  read-only open, and a backup of the database before the deploy.

## 6. Checklist for the next app

1. Copy `tracker/push.py`, the routes, the two tables, `sw.js`, `push.js` and the Settings panel.
2. Set the site address (`GB_SITE_URL` here) and the tap destination per notification.
3. Confirm `sw.js` and the page are served `no-cache` and that the outside world still gets the
   login redirect for every route, including `sw.js`.
4. On the phone: add to home screen, open from there, turn on, send a test, tap it, and check the
   panel shows "opened".
5. Only then rely on it for scheduled messages.
