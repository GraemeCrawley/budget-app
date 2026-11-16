-- 3 -> 4: the app's own phone notifications. A subscription is one phone's address at its push service.
-- A notification row records when it was sent, when a phone reported receiving it, and when it was opened.
CREATE TABLE push_subscriptions (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  endpoint TEXT NOT NULL UNIQUE, p256dh TEXT NOT NULL, auth TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE notifications (
  id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL, sent_at TEXT NOT NULL, phones INTEGER NOT NULL,
  delivered_at TEXT, opened_at TEXT
);
