-- 4 -> 5: the plan. The savings-rate target the owner measures against, and a budget for any
-- category, by the month or by the year.
CREATE TABLE plan_settings (
  user_id INTEGER PRIMARY KEY REFERENCES users(id),
  target REAL NOT NULL CHECK (target >= 0 AND target <= 0.9)
);
CREATE TABLE budgets (
  user_id INTEGER NOT NULL REFERENCES users(id),
  category TEXT NOT NULL,
  cents INTEGER NOT NULL CHECK (cents > 0),
  period TEXT NOT NULL CHECK (period IN ('month', 'year')),
  PRIMARY KEY (user_id, category)
);
