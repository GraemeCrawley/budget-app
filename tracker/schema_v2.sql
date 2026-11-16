-- 1 -> 2: corrections. overrides is rebuilt (SQLite cannot add a CHECK to a table), keyed to its user.
CREATE TABLE overrides_new (
  transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  kind TEXT CHECK (kind IS NULL OR kind IN ('spending','income','transfer','saving','bucket','offset')),
  category TEXT,
  one_off INTEGER CHECK (one_off IS NULL OR one_off IN (0, 1)),
  set_at TEXT NOT NULL
);
INSERT INTO overrides_new (transaction_id, user_id, kind, category, one_off, set_at)
  SELECT o.transaction_id, t.user_id, o.kind, o.category, o.one_off, ''
  FROM overrides o JOIN transactions t ON t.id = o.transaction_id;
DROP TABLE overrides;
ALTER TABLE overrides_new RENAME TO overrides;

ALTER TABLE rules ADD COLUMN merchant_key TEXT;  -- NULL = not a merchant rule
ALTER TABLE accounts ADD COLUMN flip_sign INTEGER NOT NULL DEFAULT 0;
ALTER TABLE accounts ADD COLUMN export_note TEXT NOT NULL DEFAULT '';
ALTER TABLE transactions ADD COLUMN matched_id INTEGER REFERENCES transactions(id);

CREATE TABLE month_reviews (
  user_id INTEGER NOT NULL REFERENCES users(id),
  month TEXT NOT NULL,
  reviewed_at TEXT NOT NULL,
  income_cents INTEGER NOT NULL,
  spending_cents INTEGER NOT NULL,
  PRIMARY KEY (user_id, month)
);
