CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  key TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, institution TEXT NOT NULL,
  UNIQUE(user_id, key));
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  connector TEXT NOT NULL, connector_version INTEGER NOT NULL, format_version INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('statement','activity')),
  period_start TEXT NOT NULL, period_end TEXT NOT NULL,
  opening_cents INTEGER, closing_cents INTEGER,
  source_name TEXT NOT NULL, sha256 TEXT NOT NULL, raw BLOB NOT NULL,
  received_at TEXT NOT NULL,
  UNIQUE(user_id, account_id, sha256));
CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  batch_id INTEGER NOT NULL REFERENCES batches(id),
  uid TEXT NOT NULL, date TEXT NOT NULL, amount_cents INTEGER NOT NULL, description TEXT NOT NULL,
  provisional INTEGER NOT NULL, superseded_by INTEGER REFERENCES batches(id),
  UNIQUE(account_id, uid));
CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  priority INTEGER NOT NULL,            -- lower runs first
  pattern TEXT NOT NULL,                -- regular expression, matched case-insensitively against the description; '' matches all
  account_key TEXT,                     -- NULL = any account
  sign INTEGER,                         -- -1 money out, 1 money in, NULL either
  min_cents INTEGER, max_cents INTEGER, -- bounds on the absolute amount, NULL = none
  date_from TEXT, date_to TEXT,         -- inclusive bounds, NULL = none
  kind TEXT NOT NULL CHECK (kind IN ('spending','income','transfer','saving','bucket','offset')),
  category TEXT NOT NULL,               -- '' when the kind has none
  one_off INTEGER NOT NULL DEFAULT 0,
  origin TEXT NOT NULL CHECK (origin IN ('seed','owner')),
  label TEXT NOT NULL                   -- short reason shown to the owner, e.g. 'grocery stores'
);
CREATE TABLE IF NOT EXISTS overrides (
  transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id),
  kind TEXT, category TEXT, one_off INTEGER
);
