// An invented ledger that answers every /api/v1 endpoint the client uses, for `VITE_MOCK=1 npm run dev`
// and visual checks. Nothing here is real: merchants, accounts and amounts are made up.
//
// Shape: `state` holds accounts, batches, transactions (each with a `base` classification), merchant
// rules, overrides and reviews. Every read is computed from `state` the way the server computes it,
// so a write (an override, a rule, an upload) changes the totals that Home shows.
// `answer(method, path, body)` resolves to `{status, body}`; api.js turns 4xx/5xx into ApiError.
// To extend: add a route to ROUTES (method, a regex on the path, a handler taking the match groups,
// the query and the body). Set `globalThis.__mockFail = true` in the console to fail every request
// as a network failure would (status 0, which the client reads as an expired sign-in: the login
// redirect fails a request that way), or `globalThis.__mockSignedOut = true` to answer every request
// with the server's 401, until it is set back to false.
// Uploads: the uploaded file's name picks the outcome (every refusal, a duplicate, a statement with
// confirmations, differences and a warning); see the table above takeUpload().

const TODAY = "2026-11-13";
const BIG_PURCHASE_CENTS = 20000;
const KINDS = ["spending", "income", "transfer", "saving", "bucket", "offset"];
const SPENDING_LIKE = ["spending", "bucket", "offset"];
const BLOCKS = ["Food", "Bills", "Subscriptions", "Big purchases", "Buckets", "Everything else"];
const CATEGORY_BLOCK = {
  Groceries: "Food", "Dining & delivery": "Food", Coffee: "Food", "Bars & alcohol": "Food",
  Rent: "Bills", "Utilities & internet": "Bills", Phone: "Bills", "Fees & interest": "Bills", Insurance: "Bills",
  Subscriptions: "Subscriptions",
};
const FOOD_AT_HOME = ["Groceries"];
const CATEGORIES = [...Object.keys(CATEGORY_BLOCK), "Transport", "Travel", "Entertainment", "Gifts", "Personal care",
  "Home", "Clothes", "Books & music", "Shopping", "Games", "Can't remember"];
const MONTHS = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"];
const CARD_THROUGH = "2026-10-18"; // October is incomplete: the card is behind

// ---- dates ---------------------------------------------------------------------------------------

function lastDay(ym) {
  return `${ym}-${String(new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(5, 7), 0)).getUTCDate()).padStart(2, "0")}`;
}

function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

// ---- the invented ledger -------------------------------------------------------------------------

function seed() {
  const s = {
    accounts: [
      { key: "chequing", name: "Everyday chequing", kind: "chequing", institution: "Sample Bank",
        export_note: "Accounts, then Download, then CSV for last month.", flip_sign: 0 },
      { key: "card", name: "Card", kind: "card", institution: "Sample Bank", export_note: "", flip_sign: 0 },
      { key: "savings", name: "Savings", kind: "savings", institution: "Sample Bank", export_note: "",
        flip_sign: 0 },
    ],
    batches: [], transactions: [], rules: {}, overrides: {}, reviews: {}, uploads: [],
    nextId: 1, nextBatch: 1,
  };
  for (const ym of MONTHS) {
    for (const acct of s.accounts) {
      // The card's October is an activity export to Oct 18, not yet a statement: its rows are provisional.
      const partial = acct.key === "card" && ym === "2026-10";
      const end = partial ? CARD_THROUGH : lastDay(ym);
      s.batches.push({ id: s.nextBatch++, account: acct.key, kind: partial ? "activity" : "statement",
        period_start: `${ym}-01`, period_end: end, received: addDays(end, 3) });
    }
  }

  const add = (date, cents, description, account, merchant, base, extra = {}) => {
    if (account === "card" && date > CARD_THROUGH) return;
    const batch = s.batches.find((b) => b.account === account && b.period_start <= date && date <= b.period_end);
    s.transactions.push({ id: s.nextId++, date, amount_cents: cents, description, account, merchant, batch: batch.id,
      base: { one_off: false, guessed: false, ...base }, provisional: batch.kind === "activity", superseded: false,
      ...extra });
  };
  const rule = (label, kind, category) => ({ kind, category, why: `rule: ${label}` });

  MONTHS.forEach((ym, i) => {
    const d = (day) => `${ym}-${String(day).padStart(2, "0")}`;
    // income and saving
    // The first month has a single small deposit, so its rate is far below -100% (shown off the chart).
    add(d(1), i === 0 ? 50000 : 210000, "NORTHWIND PAYROLL DEP", "chequing", "NORTHWIND PAYROLL", { ...rule("payroll", "income", "") });
    if (i > 0) add(d(15), 210000, "NORTHWIND PAYROLL DEP", "chequing", "NORTHWIND PAYROLL", { ...rule("payroll", "income", "") });
    add(d(16), -60000, "TRANSFER TO SAVINGS", "chequing", "", { ...rule("own transfer", "saving", "") });
    add(d(16), 60000, "TRANSFER FROM CHEQUING", "savings", "", { ...rule("own transfer", "transfer", "") });
    // bills
    add(d(1), -165000, "MAPLE COURT RENT", "chequing", "MAPLE COURT", { ...rule("rent", "spending", "Rent") });
    add(d(8), -9000, "BRIGHTWIRE INTERNET", "card", "BRIGHTWIRE", { ...rule("utilities", "spending", "Utilities & internet") });
    add(d(12), -4500, "PINEPHONE MOBILE", "card", "PINEPHONE", { ...rule("phone", "spending", "Phone") });
    add(d(20), -2000, "STREAMCO MONTHLY", "card", "STREAMCO", { ...rule("subscriptions", "spending", "Subscriptions") });
    add(d(22), -500, "CLOUDBOX STORAGE", "card", "CLOUDBOX", { ...rule("subscriptions", "spending", "Subscriptions") });
    // food
    [3, 10, 17, 24].forEach((day, k) =>
      add(d(day), -(9000 + 1000 * ((i + k) % 3)), "GREEN GROCER 114", "card", "GREEN GROCER",
        { ...rule("grocery stores", "spending", "Groceries") }));
    [5, 9, 14, 19, 27].forEach((day) =>
      add(d(day), -650, "CORNER CAFE 0412", "card", "CORNER CAFE", { ...rule("coffee", "spending", "Coffee") }));
    [6, 21].forEach((day) =>
      add(d(day), -(4000 + 1000 * (i % 3)), "NOODLE HOUSE", "card", "NOODLE HOUSE",
        { ...rule("restaurants", "spending", "Dining & delivery") }));
    // everything else
    add(d(11), -10000, "CITY TRANSIT PASS", "card", "CITY TRANSIT", { ...rule("transit", "spending", "Transport") });
    add(d(18), -3000, "PAPER LANTERN GIFTS", "card", "PAPER LANTERN", { ...rule("gift shops", "spending", "Gifts") });
  });

  // A big purchase in July; a one-off bonus in June.
  add("2026-07-09", -45000, "HARDWARE HUT ONLINE", "card", "HARDWARE HUT", { ...rule("hardware", "spending", "Home") });
  add("2026-06-26", 50000, "NORTHWIND BONUS", "chequing", "NORTHWIND PAYROLL",
    { ...rule("payroll", "income", ""), one_off: true });
  // September: two uncategorised charges, one unconfirmed income row, and charges not yet on a statement.
  // the real server also marks spending it could not place as `guessed`
  const noRule = { kind: "spending", category: "Uncategorised", why: "no rule matched", guessed: true };
  add("2026-09-12", -2400, "BOOK BARN 22", "card", "BOOK BARN", noRule);
  add("2026-09-23", -1800, "BOOK BARN 22", "card", "BOOK BARN", noRule);
  add("2026-09-19", 15000, "E-TRANSFER RECEIVED", "chequing", "",
    { kind: "income", category: "", why: "no rule matched", guessed: true });
  add("2026-09-29", -650, "CORNER CAFE 0412", "card", "CORNER CAFE", { ...rule("coffee", "spending", "Coffee") },
    { provisional: true });
  add("2026-09-30", -3200, "NOODLE HOUSE", "card", "NOODLE HOUSE",
    { ...rule("restaurants", "spending", "Dining & delivery") }, { provisional: true });
  // October: one more uncategorised.
  add("2026-10-07", -3500, "BLUE DOOR STUDIO", "card", "BLUE DOOR STUDIO", noRule);

  return s;
}

let state;

// For tests of later screens: start again from the invented ledger.
export function reset() {
  state = seed();
  // May to August were reviewed; August has changed since (its stored spending differs).
  for (const ym of ["2026-05", "2026-06", "2026-07"]) state.reviews[ym] = totals(ym);
  state.reviews["2026-08"] = { income_cents: 420000, spending_cents: 100000 };
}

reset();

// ---- classification, as the server does it ------------------------------------------------------

function classified(t) {
  const sign = t.amount_cents < 0 ? "-" : "+";
  const r = t.merchant ? state.rules[`${t.merchant}|${sign}`] : undefined;
  let c = r ? { ...t.base, ...r, why: `rule: you said ${t.merchant}`, guessed: false } : { ...t.base };
  const o = state.overrides[t.id];
  if (o) {
    c = { ...c, guessed: false, why: "you set this" };
    if (o.kind != null) c.kind = o.kind;
    if (o.category != null) c.category = o.category;
    if (o.one_off != null) c.one_off = o.one_off;
  }
  if (SPENDING_LIKE.includes(c.kind) && !c.category) c.category = "Uncategorised";
  return c;
}

function blockOf(t, c) {
  if (c.kind === "bucket") return "Buckets";
  const block = CATEGORY_BLOCK[c.category] || "Everything else";
  if (c.kind === "spending" && t.amount_cents <= -BIG_PURCHASE_CENTS && block === "Everything else") {
    return "Big purchases";
  }
  return block;
}

function accountName(key) {
  return state.accounts.find((a) => a.key === key)?.name ?? key;
}

function txObject(t) {
  const c = classified(t);
  return { id: t.id, date: t.date, amount_cents: t.amount_cents, description: t.description,
    account: t.account, account_name: accountName(t.account), kind: c.kind, category: c.category,
    block: SPENDING_LIKE.includes(c.kind) ? blockOf(t, c) : null, one_off: c.one_off,
    provisional: t.provisional, why: c.why, guessed: c.guessed, merchant: t.merchant };
}

function live() {
  return state.transactions.filter((t) => !t.superseded);
}

function inMonth(ym) {
  return live().filter((t) => t.date.slice(0, 7) === ym);
}

function totals(ym) {
  let income = 0;
  let spending = 0;
  for (const t of inMonth(ym)) {
    const c = classified(t);
    if (c.kind === "income") income += t.amount_cents;
    else if (SPENDING_LIKE.includes(c.kind)) spending -= t.amount_cents;
  }
  return { income_cents: income, spending_cents: spending };
}

// ---- coverage ------------------------------------------------------------------------------------

function coverage() {
  const out = {};
  for (const b of [...state.batches].sort((x, y) => x.period_start.localeCompare(y.period_start))) {
    const ranges = (out[b.account] ||= []);
    const last = ranges[ranges.length - 1];
    if (last && b.period_start <= addDays(last[1], 1)) {
      if (b.period_end > last[1]) last[1] = b.period_end;
    } else {
      ranges.push([b.period_start, b.period_end]);
    }
  }
  return out;
}

function dataThrough() {
  return Object.fromEntries(Object.entries(coverage()).map(([k, r]) => [k, r[r.length - 1][1]]));
}

function monthComplete(cov, ym) {
  const first = `${ym}-01`;
  const last = lastDay(ym);
  const judged = Object.values(cov).filter((r) => r.length && r[0][0] <= last);
  return judged.length > 0 && judged.every((r) => r.some(([s, e]) => s <= first && e >= last));
}

// ---- reads ---------------------------------------------------------------------------------------

function monthFacts() {
  const cov = coverage();
  const months = [...new Set(live().map((t) => t.date.slice(0, 7)))].sort();
  return months.map((ym) => {
    let income = 0, saving = 0, foodOut = 0, foodHome = 0;
    let uncategorised = 0, unconfirmed = 0, oneOffIncome = false, oneOffSpending = false, provisional = false;
    const blocks = Object.fromEntries(BLOCKS.map((b) => [b, 0]));
    const categories = {};
    for (const t of inMonth(ym)) {
      const c = classified(t);
      provisional ||= t.provisional;
      if (c.kind === "income") {
        income += t.amount_cents;
        oneOffIncome ||= c.one_off;
        if (c.guessed) unconfirmed += 1;
      } else if (c.kind === "saving") {
        saving -= t.amount_cents;
      } else if (SPENDING_LIKE.includes(c.kind)) {
        blocks[blockOf(t, c)] -= t.amount_cents;
        const within = (categories[blockOf(t, c)] ??= {});
        within[c.category] = (within[c.category] ?? 0) - t.amount_cents;
        oneOffSpending ||= c.kind === "spending" && c.one_off && t.amount_cents < 0;
        if (c.kind !== "bucket" && CATEGORY_BLOCK[c.category] === "Food") {
          if (FOOD_AT_HOME.includes(c.category)) foodHome -= t.amount_cents;
          else foodOut -= t.amount_cents;
        }
      }
      if (c.category === "Uncategorised" && !["transfer", "income", "saving"].includes(c.kind)) uncategorised += 1;
    }
    const spending = Object.values(blocks).reduce((a, b) => a + b, 0);
    const stored = state.reviews[ym];
    return {
      month: ym, income_cents: income, spending_cents: spending, saving_cents: saving,
      savings_rate: income > 0 ? Math.round(((income - spending) / income) * 10000) / 10000 : null,
      blocks, categories, food_out_cents: foodOut, food_home_cents: foodHome, complete: monthComplete(cov, ym),
      provisional, one_off_income: oneOffIncome, one_off_spending: Boolean(oneOffSpending), uncategorised_count: uncategorised,
      unconfirmed_income_count: unconfirmed, reviewed: Boolean(stored),
      changed_since_review: Boolean(stored) && (stored.income_cents !== income || stored.spending_cents !== spending),
    };
  });
}

function oneMonth(ym) {
  const facts = monthFacts().find((m) => m.month === ym);
  if (!facts) return [404, { detail: "no data for that month" }];
  const groups = {};
  for (const t of inMonth(ym)) {
    const c = classified(t);
    if (!SPENDING_LIKE.includes(c.kind)) continue;
    const key = `${c.category}|${blockOf(t, c)}`;
    groups[key] ||= { category: c.category, block: blockOf(t, c), cents: 0, count: 0 };
    groups[key].cents -= t.amount_cents;
    groups[key].count += 1;
  }
  const categories = Object.values(groups).sort((a, b) => b.cents - a.cents || a.category.localeCompare(b.category));
  return [200, { ...facts, categories }];
}

function newestFirst(a, b) {
  return b.date.localeCompare(a.date) || b.id - a.id;
}

function transactions(q) {
  if (q.month && !/^\d{4}-(0[1-9]|1[0-2])$/.test(q.month)) return [422, { detail: "month is not a month" }];
  if (q.block && !BLOCKS.includes(q.block)) return [422, { detail: "unknown block" }];
  const rows = (q.month ? inMonth(q.month) : live()).map(txObject)
    .filter((t) => (!q.block || t.block === q.block) && (!q.category || t.category === q.category));
  return [200, { transactions: rows.sort(newestFirst) }];
}

function findTx(id) {
  return live().find((t) => t.id === Number(id));
}

function sameMerchant(t) {
  const sign = Math.sign(t.amount_cents);
  return live().filter((x) => x.merchant && x.merchant === t.merchant && Math.sign(x.amount_cents) === sign);
}

function oneTx(id) {
  const t = findTx(id);
  if (!t) return [404, { detail: "no such transaction" }];
  return [200, { ...txObject(t), merchant_charges: t.merchant ? sameMerchant(t).length : 0 }];
}

function categories() {
  const used = [...Object.values(state.rules), ...Object.values(state.overrides)]
    .map((r) => r.category).filter(Boolean);
  const all = [...new Set([...CATEGORIES, ...used])].sort();
  return [200, { categories: all, blocks: Object.fromEntries(all.map((c) => [c, CATEGORY_BLOCK[c] || "Everything else"])) }];
}

function review(q) {
  if (q.month && !/^\d{4}-(0[1-9]|1[0-2])$/.test(q.month)) return [422, { detail: "month is malformed" }];
  const ym = q.month || null; // no month: what needs a decision across every month
  const rows = (ym ? inMonth(ym) : live()).map((t) => ({ t, tx: txObject(t) }));
  const unplaced = {};
  const recognised = {};
  for (const { t, tx } of rows) {
    if (!SPENDING_LIKE.includes(tx.kind)) continue;
    if (tx.category === "Uncategorised") { // by merchant and sign: a group's charges are all out or all in
      const g = (unplaced[`${tx.merchant}|${tx.amount_cents > 0}`] ||= { merchant: tx.merchant, count: 0, cents: 0, charges: [] });
      g.count += 1;
      g.cents -= tx.amount_cents;
      g.charges.push(tx);
    } else if (ym) {
      const g = (recognised[tx.category] ||= { category: tx.category, block: tx.block, cents: 0, charges: [] });
      g.cents -= tx.amount_cents;
      const firstTime = Boolean(t.merchant) && !live().some((x) => x.merchant === t.merchant && x.date.slice(0, 7) < ym);
      g.charges.push({ ...tx, first_time: firstTime });
    }
  }
  for (const g of Object.values(recognised)) {
    g.charges.sort((a, b) => Number(b.first_time) - Number(a.first_time) || a.amount_cents - b.amount_cents);
  }
  return [200, {
    month: ym,
    unplaced: Object.values(unplaced).sort((a, b) => b.cents - a.cents),
    unconfirmed_income: rows.map((r) => r.tx).filter((tx) => tx.kind === "income" && tx.guessed),
    recognised: Object.values(recognised).sort((a, b) => b.cents - a.cents),
    reviewed: ym ? Boolean(state.reviews[ym]) : false,
  }];
}

function accountView(a) {
  const ranges = coverage()[a.key] || [];
  return { key: a.key, name: a.name, kind: a.kind, institution: a.institution, export_note: a.export_note,
    data_through: ranges.length ? ranges[ranges.length - 1][1] : null, ranges, flip_sign: a.flip_sign };
}

// ---- writes --------------------------------------------------------------------------------------

// The server's category rule: trimmed, 1 to 40 characters, no control characters, not "Uncategorised";
// an existing category matched ignoring case keeps its spelling. Returns [name] or [null, detail].
function cleanCategory(raw) {
  const name = String(raw ?? "").trim();
  if (!name) return [null, "category must not be empty"];
  if (name.length > 40) return [null, "category must be 40 characters or fewer"];
  if (/\p{Cc}/u.test(name)) return [null, "category must not contain control characters"];
  if (name.toLowerCase() === "uncategorised") return [null, "Uncategorised is reserved; pick another name"];
  const known = categories()[1].categories.find((c) => c.toLowerCase() === name.toLowerCase());
  return [known ?? name];
}

function putOverride(id, body) {
  const t = findTx(id);
  if (!t) return [404, { detail: "no such transaction" }];
  if ("kind" in body && body.kind !== null && !KINDS.includes(body.kind)) return [422, { detail: "unknown kind" }];
  if ("category" in body && body.category !== null) {
    const [name, detail] = cleanCategory(body.category);
    if (name === null) return [422, { detail }];
    body = { ...body, category: name };
  }
  const o = { kind: null, category: null, one_off: null, ...state.overrides[t.id] };
  for (const field of ["kind", "category", "one_off"]) if (field in body) o[field] = body[field];
  if (o.kind === null && o.category === null && o.one_off === null) delete state.overrides[t.id];
  else state.overrides[t.id] = o;
  return [200, txObject(t)];
}

function deleteOverride(id) {
  const t = findTx(id);
  if (!t) return [404, { detail: "no such transaction" }];
  delete state.overrides[t.id];
  return [200, txObject(t)];
}

function merchantRule(id, body) {
  const t = findTx(id);
  if (!t) return [404, { detail: "no such transaction" }];
  if (!t.merchant) return [422, { detail: "no merchant" }];
  if (!KINDS.includes(body.kind)) return [422, { detail: "unknown kind" }];
  const spendingLike = SPENDING_LIKE.includes(body.kind);
  if (spendingLike) {
    const [name, detail] = cleanCategory(body.category);
    if (name === null) return [422, { detail }];
    body = { ...body, category: name };
  }
  const sign = t.amount_cents < 0 ? "-" : "+";
  state.rules[`${t.merchant}|${sign}`] = { kind: body.kind, category: spendingLike ? body.category : "",
    one_off: Boolean(body.one_off) };
  const o = state.overrides[t.id]; // the charge's own kind and category give way; its one-off mark stays
  if (o && o.one_off != null) state.overrides[t.id] = { kind: null, category: null, one_off: o.one_off };
  else delete state.overrides[t.id];
  return [200, { merchant: t.merchant, charges: sameMerchant(t).length }];
}

function markReviewed(ym) {
  state.reviews[ym] = totals(ym);
  return [200, { month: ym, reviewed: true }];
}

function slug(name) {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function createAccount(body) {
  const name = (body.name || "").trim();
  if (!name) return [422, { detail: "an account needs a name" }];
  if (!["chequing", "card", "savings", "investment"].includes(body.kind)) return [422, { detail: "unknown kind" }];
  const key = slug(name);
  if (state.accounts.some((a) => a.key === key)) return [409, { detail: "an account with that name already exists" }];
  const a = { key, name, kind: body.kind, institution: body.institution || "", export_note: "", flip_sign: 0 };
  state.accounts.push(a);
  return [201, accountView(a)];
}

function patchAccount(key, body) {
  const a = state.accounts.find((x) => x.key === key);
  if (!a) return [404, { detail: "no such account" }];
  if (typeof body.export_note === "string") a.export_note = body.export_note;
  if (typeof body.name === "string" && body.name.trim()) a.name = body.name.trim();
  return [200, accountView(a)];
}

function batchSummary(b, extra) {
  const ym = b.period_end.slice(0, 7);
  return { id: b.id, account: b.account, account_name: accountName(b.account), kind: b.kind,
    period_start: b.period_start, period_end: b.period_end, status: "accepted", added: 0, already_held: 0,
    confirmed: 0, differences: [], message: "",
    can_widen: b.kind === "activity" && (!b.period_start.endsWith("-01") || b.period_end !== lastDay(ym)),
    ...extra };
}

// The mock cannot read files, so the uploaded file's name picks the outcome (first match wins):
//   "huge"          413 too_large
//   "bad"           422 failed_checks
//   "mismatch"      422 kind_mismatch
//   "unknown"       422 no_format
//   no account_key  with "needs-account": 422 account_needed, needs.choose_account;
//                   with "wrong": the file is for Everyday chequing; otherwise it is for the Card
//   "wrong"         with an account_key other than chequing: 422 wrong_account, needs.file_is_for
//   "flipped"       on a card with flip_sign off and no `signs`: 422 signs_look_reversed, needs.choose_signs
//                   (`signs=flip` turns flip_sign on; `signs=as_is` goes ahead)
//   "dup", or the same name sent again for the same account: 200, batch status "duplicate"
//   "statement"     200, a statement for the whole month holding the account's data-through date; it
//                   confirms that month's provisional charges, reports one "only in the statement" row,
//                   and, when the account already holds a statement for that month, the warning message
//   anything else   200, an activity export from the day after the account's data to two days before
//                   that month's end (so can_widen), with up to three invented provisional charges
// A refusal is {ok: false, code, reason, needs} and stores nothing.
const REASONS = { // the server's own sentences (tracker/uploads.py REASONS), shown to the owner as given
  too_large: "This file is larger than 10 MB, the most the tracker takes.",
  failed_checks: "The file was read, but it failed the tracker's checks, so nothing was stored.",
  kind_mismatch: "This file is for a kind of account different from the kind already held under that account.",
  no_format: "This file is not in a format the tracker knows.",
  account_needed: "This file does not say which account it is for. Choose the account.",
  wrong_account: "This file is for a different account than the one chosen.",
  signs_look_reversed: "Most rows in this card export are money in. Charges may be shown as positive numbers. Say whether to flip the signs.",
};

function refuse(code, needs = null, status = 422) {
  return [status, { ok: false, code, reason: REASONS[code], needs }];
}

function newRow(account, batch, date, cents, description, merchant, provisional) {
  const known = live().find((t) => t.merchant === merchant);
  state.transactions.push({ id: state.nextId++, date, amount_cents: cents, description, account, merchant, batch,
    base: known ? { ...known.base } : { kind: "spending", category: "Uncategorised", why: "no rule matched",
      one_off: false, guessed: false },
    provisional, superseded: false });
}

// An invented charge on an account, for tests and the console.
export function addCharge(account, date, cents, description, merchant) {
  const b = state.batches.filter((x) => x.account === account).at(-1);
  newRow(account, b ? b.id : null, date, cents, description, merchant, false);
}

function takeStatement(a) {
  const through = dataThrough()[a.key] || TODAY;
  const ym = through.slice(0, 7);
  const start = `${ym}-01`;
  const end = lastDay(ym);
  const again = state.batches.some((x) => x.account === a.key && x.kind === "statement"
    && x.period_start === start && x.period_end === end);
  const b = { id: state.nextBatch++, account: a.key, kind: "statement", period_start: start, period_end: end,
    received: TODAY };
  state.batches.push(b);
  let confirmed = 0;
  for (const t of live()) {
    if (t.account === a.key && t.provisional && t.date >= start && t.date <= end) {
      t.provisional = false;
      confirmed += 1;
    }
  }
  const differences = [];
  const extra = addDays(through, 1);
  if (extra <= end) {
    newRow(a.key, b.id, extra, -3000, "PAPER LANTERN GIFTS", "PAPER LANTERN", false);
    differences.push(`only in the statement: ${extra}`);
  }
  // added is every charge on the statement, as the server counts it: those it confirmed and any new
  return [200, { ok: true, batches: [batchSummary(b, { added: confirmed + differences.length, confirmed, differences,
    message: again ? "this account already has a different statement for this period" : "" })] }];
}

function takeUpload(form) {
  const file = form.get("file");
  const filename = (file && typeof file === "object" ? file.name : String(file || "")).toLowerCase();
  const has = (word) => filename.includes(word);
  const signs = form.get("signs");
  if (has("huge")) return refuse("too_large", null, 413);
  if (has("bad")) return refuse("failed_checks");
  if (has("mismatch")) return refuse("kind_mismatch");
  if (has("unknown")) return refuse("no_format");
  let key = form.get("account_key");
  if (!key) {
    if (has("needs-account")) return refuse("account_needed", { choose_account: true });
    key = has("wrong") ? "chequing" : "card"; // the file names its own account
  }
  const a = state.accounts.find((x) => x.key === key);
  if (!a) return refuse("account_needed", { choose_account: true });
  if (has("wrong") && a.key !== "chequing") return refuse("wrong_account", { file_is_for: accountName("chequing") });
  if (has("flipped") && a.kind === "card" && !a.flip_sign && !signs) {
    return refuse("signs_look_reversed", { choose_signs: true });
  }
  if (signs === "flip") a.flip_sign = 1;
  const seen = `${a.key}|${filename}`;
  if (has("dup") || state.uploads.includes(seen)) {
    const b = state.batches.filter((x) => x.account === a.key).at(-1);
    return [200, { ok: true, batches: [batchSummary(b, { status: "duplicate", can_widen: false })] }];
  }
  state.uploads.push(seen);
  if (has("statement")) return takeStatement(a);
  const through = dataThrough()[a.key];
  const start = through ? addDays(through, 1) : `${TODAY.slice(0, 7)}-01`;
  const monthEnd = lastDay(start.slice(0, 7));
  const end = addDays(monthEnd, -2) >= start ? addDays(monthEnd, -2) : monthEnd;
  const b = { id: state.nextBatch++, account: a.key, kind: "activity", period_start: start, period_end: end,
    received: TODAY };
  state.batches.push(b);
  const invented = [[0, -1200, "CORNER CAFE 0412", "CORNER CAFE"], [1, -6400, "GREEN GROCER 114", "GREEN GROCER"],
    [2, -2700, "LANTERN BOOKS", "LANTERN BOOKS"]];
  let added = 0;
  for (const [offset, cents, description, merchant] of invented) {
    const date = addDays(start, offset);
    if (date > end) continue;
    newRow(a.key, b.id, date, cents, description, merchant, true);
    added += 1;
  }
  return [200, { ok: true, batches: [batchSummary(b, { added, already_held: 2 })] }];
}

// Only an activity batch, only widening, never past the day it was received, and neither bound more
// than 45 days beyond the batch's rows. Each refusal is a 422 with a plain detail.
function patchPeriod(id, body) {
  const b = state.batches.find((x) => x.id === Number(id));
  if (!b) return [404, { detail: "no such batch" }];
  const { period_start: start, period_end: end } = body;
  const date = /^\d{4}-\d{2}-\d{2}$/;
  if (!date.test(start || "") || !date.test(end || "") || start > end) {
    return [422, { detail: "Those dates aren't a valid range." }];
  }
  if (b.kind !== "activity") return [422, { detail: "Only an export's dates can be widened, not a statement's." }];
  if (start > b.period_start || end < b.period_end) {
    return [422, { detail: "The new dates must include the dates the file already covers." }];
  }
  if (end > b.received) return [422, { detail: "The file can't cover days after it was added." }];
  const days = state.transactions.filter((t) => t.batch === b.id).map((t) => t.date).sort();
  const first = days[0] ?? b.period_start;
  const last = days.at(-1) ?? b.period_end;
  if (start < addDays(first, -45) || end > addDays(last, 45)) {
    return [422, { detail: "That is more than 45 days beyond the charges in this file." }];
  }
  b.period_start = start;
  b.period_end = end;
  return [200, batchSummary(b)];
}

// reminders on the phone: how many phones are subscribed, and the last notification sent
const push = { phones: 0, last: null };
// the plan: the savings target and a couple of budgets to look at
const plan = { target: 0.15, budgets: [{ category: "Groceries", cents: 45000, period: "month" },
  { category: "Dining & delivery", cents: 12000, period: "month" }, { category: "Travel", cents: 200000, period: "year" }] };

// ---- routing -------------------------------------------------------------------------------------

const YM = "(\\d{4}-(?:0[1-9]|1[0-2]))";
const ROUTES = [
  ["GET", "me", () => [200, { user: "owner", login_check: "enforce" }]],
  ["GET", "months", () => [200, { months: monthFacts(), data_through: dataThrough(), target: plan.target }]],
  ["GET", `months/${YM}`, (m) => oneMonth(m[1])],
  ["POST", `months/${YM}/reviewed`, (m) => markReviewed(m[1])],
  ["GET", "transactions", (m, q) => transactions(q)],
  ["GET", "transactions/(\\d+)", (m) => oneTx(m[1])],
  ["PUT", "transactions/(\\d+)/override", (m, q, body) => putOverride(m[1], body || {})],
  ["DELETE", "transactions/(\\d+)/override", (m) => deleteOverride(m[1])],
  ["POST", "transactions/(\\d+)/merchant-rule", (m, q, body) => merchantRule(m[1], body || {})],
  ["GET", "categories", () => categories()],
  ["GET", "review", (m, q) => review(q)],
  ["GET", "accounts", () => [200, { accounts: state.accounts.map(accountView) }]],
  ["GET", "coverage", () => [200, { accounts: state.accounts.map(accountView) }]],
  ["POST", "accounts", (m, q, body) => createAccount(body || {})],
  ["PATCH", "accounts/([a-z0-9-]+)", (m, q, body) => patchAccount(m[1], body || {})],
  ["POST", "uploads", (m, q, body) => takeUpload(body)],
  ["PATCH", "batches/(\\d+)/period", (m, q, body) => patchPeriod(m[1], body || {})],
  ["GET", "plan", () => [200, plan]],
  ["PUT", "plan/target", (m, q, body) => { plan.target = body.target; return [200, plan]; }],
  ["PUT", "plan/budgets", (m, q, body) => {
    if (!(body.cents > 0)) return [422, { detail: "a budget is an amount above zero" }];
    plan.budgets = [...plan.budgets.filter((b) => b.category !== body.category), body];
    return [200, plan];
  }],
  ["DELETE", "plan/budgets", (m, q, body) => {
    plan.budgets = plan.budgets.filter((b) => b.category !== body.category);
    return [200, plan];
  }],
  ["GET", "push", () => [200, { key: "mock-key", phones: push.phones, last: push.last }]],
  ["POST", "push/subscriptions", () => { push.phones = 1; return [200, { phones: 1 }]; }],
  ["DELETE", "push/subscriptions", () => { push.phones = 0; return [200, { phones: 0 }]; }],
  ["POST", "push/test", () => {
    if (!push.phones) return [409, { detail: "no phone has reminders turned on yet" }];
    push.last = { kind: "test", sent_at: new Date().toISOString(), phones: 1, delivered_at: null, opened_at: null };
    return [200, { id: "mock", sent: 1, failed: 0 }];
  }],
  ["POST", "push/events", () => [204, null]],
].map(([method, pattern, handle]) => [method, new RegExp(`^${pattern}$`), handle]);

export function route(method, path, body) {
  const [pathname, search = ""] = path.split("?");
  const query = Object.fromEntries(new URLSearchParams(search));
  const hit = ROUTES.find(([m, re]) => m === method && re.test(pathname));
  if (!hit) return { status: 404, body: { detail: "Not Found" } };
  const [status, out] = hit[2](pathname.match(hit[1]), query, body);
  return { status, body: JSON.parse(JSON.stringify(out)) }; // a copy, as if it came over the wire
}

export async function answer(method, path, body) {
  await new Promise((resolve) => setTimeout(resolve, 250)); // long enough to see the loading state
  if (globalThis.__mockFail) throw new TypeError("mock network failure");
  if (globalThis.__mockSignedOut) return { status: 401, body: { detail: "not signed in", reason: "expired" } };
  return route(method, path, body);
}
