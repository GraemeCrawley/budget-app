import { beforeEach, describe, expect, it } from "vitest";
import { addCharge, answer, reset, route } from "./mock.js";

const ok = (method, path, body) => {
  const res = route(method, path, body);
  expect(res.status).toBeLessThan(300);
  return res.body;
};

beforeEach(() => reset());

function form(name, fields) {
  const f = new FormData();
  f.append("file", new File(["x"], name));
  for (const [k, v] of Object.entries(fields)) f.append(k, v);
  return f;
}

function refusal(name, fields) {
  const { status, body } = route("POST", "uploads", form(name, fields));
  return [status, body.code, body.needs];
}

describe("mock", () => {
  it("holds six months: one incomplete, one provisional, with charges to look at", () => {
    const { months, data_through } = ok("GET", "months");
    expect(months.map((m) => m.month)).toEqual(["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]);
    expect(months.filter((m) => !m.complete).map((m) => m.month)).toEqual(["2026-10"]);
    // September is complete but not all confirmed; October's card rows are from an export, not a statement.
    expect(months.filter((m) => m.provisional).map((m) => m.month)).toEqual(["2026-09", "2026-10"]);
    const sep = months[4];
    expect([sep.uncategorised_count, sep.unconfirmed_income_count]).toEqual([2, 1]);
    expect(months.find((m) => m.month === "2026-08").changed_since_review).toBe(true);
    expect(data_through.card).toBe("2026-10-18");
    for (const m of months) expect(Number.isInteger(m.spending_cents)).toBe(true);
  });

  it("seeds a month far below -100% and a month with a one-off deposit", () => {
    const { months } = ok("GET", "months");
    expect(months.filter((m) => m.savings_rate < -1).map((m) => m.month)).toEqual(["2026-05"]);
    expect(months.filter((m) => m.one_off_income).map((m) => m.month)).toEqual(["2026-06"]);
  });

  it("answers every endpoint the client uses", () => {
    ok("GET", "me");
    ok("GET", "months/2026-09");
    ok("GET", "transactions?month=2026-09&block=Food");
    ok("GET", "transactions/1");
    ok("GET", "categories");
    ok("GET", "review?month=2026-09");
    ok("GET", "accounts");
    ok("GET", "coverage");
    expect(route("GET", "nope").status).toBe(404);
  });

  it("an override changes the month's totals, and undoing it restores them", () => {
    const before = ok("GET", "months").months[4];
    const [book] = ok("GET", "review?month=2026-09").unplaced[0].charges;
    expect(ok("PUT", `transactions/${book.id}/override`, { category: "Shopping" }).why).toBe("you set this");
    expect(ok("GET", "months").months[4].uncategorised_count).toBe(1);
    ok("PUT", `transactions/${book.id}/override`, { kind: "transfer" });
    expect(ok("GET", "months").months[4].spending_cents).toBe(before.spending_cents + book.amount_cents);
    ok("DELETE", `transactions/${book.id}/override`);
    expect(ok("GET", "months").months[4]).toEqual(before);
    expect(route("PUT", `transactions/${book.id}/override`, { kind: "nonsense" }).status).toBe(422);
  });

  it("a merchant rule places every charge from that merchant", () => {
    const [group] = ok("GET", "review?month=2026-09").unplaced;
    expect(group).toMatchObject({ merchant: "BOOK BARN", count: 2, cents: 4200 });
    expect(ok("POST", `transactions/${group.charges[0].id}/merchant-rule`, { kind: "spending", category: "Shopping" }))
      .toEqual({ merchant: "BOOK BARN", charges: 2 });
    expect(ok("GET", "review?month=2026-09").unplaced).toEqual([]);
  });

  it("a spending merchant rule needs a category, another kind stores none, and a one-off charge stays one-off", () => {
    const [group] = ok("GET", "review?month=2026-09").unplaced;
    const id = group.charges[0].id;
    expect(route("POST", `transactions/${id}/merchant-rule`, { kind: "spending" }).status).toBe(422);
    expect(route("POST", `transactions/${id}/merchant-rule`, { kind: "bucket", category: "" }).status).toBe(422);
    ok("PUT", `transactions/${id}/override`, { category: "Gifts", one_off: true });
    ok("POST", `transactions/${id}/merchant-rule`, { kind: "spending", category: "Shopping" });
    expect(ok("GET", `transactions/${id}`)).toMatchObject({ category: "Shopping", one_off: true });
    ok("POST", `transactions/${id}/merchant-rule`, { kind: "transfer", category: "Shopping" });
    expect(ok("GET", `transactions/${id}`)).toMatchObject({ kind: "transfer", category: "" });
  });

  it("review groups a merchant's charges and refunds apart, one sign each", () => {
    const [group] = ok("GET", "review?month=2026-09").unplaced;
    const charge = ok("GET", `transactions/${group.charges[0].id}`);
    const before = ok("GET", "review?month=2026-09").unplaced.length;
    addCharge(charge.account, charge.date, 500, `${charge.merchant} REFUND`, charge.merchant);
    const groups = ok("GET", "review?month=2026-09").unplaced.filter((g) => g.merchant === charge.merchant);
    expect(groups).toHaveLength(2);
    for (const g of groups) expect(new Set(g.charges.map((c) => c.amount_cents > 0)).size).toBe(1);
    expect(ok("GET", "review?month=2026-09").unplaced).toHaveLength(before + 1);
  });

  it("a request while signed out is a 401 like the server's", async () => {
    globalThis.__mockSignedOut = true;
    try {
      expect(await answer("GET", "months")).toEqual({ status: 401, body: { detail: "not signed in", reason: "expired" } });
    } finally {
      globalThis.__mockSignedOut = false;
    }
  });

  it("marking a month reviewed clears its changed flag", () => {
    ok("POST", "months/2026-08/reviewed");
    expect(ok("GET", "months").months[3]).toMatchObject({ reviewed: true, changed_since_review: false });
  });

  it("an upload with no account and a plain name is for the card; a card file that looks flipped asks about signs", () => {
    const [batch] = ok("POST", "uploads", form("card-oct.csv", {})).batches;
    expect(batch).toMatchObject({ account: "card", kind: "activity", status: "accepted",
      period_start: "2026-10-19", period_end: "2026-10-29", can_widen: true });
    expect(refusal("flipped-oct.csv", { account_key: "card" })).toEqual([422, "signs_look_reversed", { choose_signs: true }]);
    expect(ok("POST", "uploads", form("flipped-oct.csv", { account_key: "card", signs: "flip" })).batches).toHaveLength(1);
    ok("PATCH", `batches/${batch.id}/period`, { period_start: "2026-10-01", period_end: "2026-10-31" });
    expect(ok("GET", "months").months.at(-1).complete).toBe(true);
  });

  it("an upload can produce every refusal, each as {ok: false, code, reason, needs}", () => {
    expect(refusal("needs-account.csv", {})).toEqual([422, "account_needed", { choose_account: true }]);
    expect(refusal("wrong-file.csv", { account_key: "card" }))
      .toEqual([422, "wrong_account", { file_is_for: "Everyday chequing" }]);
    expect(refusal("mismatch.csv", { account_key: "card" })).toEqual([422, "kind_mismatch", null]);
    expect(refusal("bad-rows.csv", { account_key: "card" })).toEqual([422, "failed_checks", null]);
    expect(refusal("unknown.pdf", { account_key: "card" })).toEqual([422, "no_format", null]);
    expect(refusal("huge.csv", { account_key: "card" })).toEqual([413, "too_large", null]);
    const res = route("POST", "uploads", form("mismatch.csv", { account_key: "card" }));
    expect(res.body.ok).toBe(false);
    expect(res.body.reason).toMatch(/\.$/);
  });

  it("a file sent again, or named dup, is a duplicate", () => {
    ok("POST", "uploads", form("card-oct.csv", { account_key: "card" }));
    expect(ok("POST", "uploads", form("card-oct.csv", { account_key: "card" })).batches[0].status).toBe("duplicate");
    expect(ok("POST", "uploads", form("dup.csv", { account_key: "chequing" })).batches[0].status).toBe("duplicate");
  });

  it("a statement confirms the earlier charges, reports differences, and warns about a second statement", () => {
    expect(ok("GET", "months").months.at(-1).provisional).toBe(true);
    const [st] = ok("POST", "uploads", form("statement-oct.pdf", { account_key: "card" })).batches;
    expect(st).toMatchObject({ kind: "statement", period_start: "2026-10-01", period_end: "2026-10-31",
      can_widen: false, message: "" });
    expect(st.confirmed).toBeGreaterThan(0);
    expect(st.added).toBe(st.confirmed + 1); // as the server says it: every charge on the statement
    expect(st.differences).toEqual(["only in the statement: 2026-10-19"]);
    const oct = ok("GET", "months").months.at(-1);
    expect(oct).toMatchObject({ complete: true, provisional: false });
    const [again] = ok("POST", "uploads", form("statement-oct-2.pdf", { account_key: "card" })).batches;
    expect(again.message).toBe("this account already has a different statement for this period");
  });

  it("only an activity batch can be widened, within the rules", () => {
    const [b] = ok("POST", "uploads", form("card-oct.csv", { account_key: "card" })).batches;
    const patch = (period_start, period_end, id = b.id) =>
      route("PATCH", `batches/${id}/period`, { period_start, period_end });
    expect(patch("2026-10-01", "2026-10-31", 1).status).toBe(422); // a statement
    expect(patch("2026-10-20", "2026-10-31").status).toBe(422); // does not contain the old range
    expect(patch("2026-10-01", "2026-11-20").status).toBe(422); // past the day it was received
    expect(patch("2026-08-01", "2026-10-31").status).toBe(422); // more than 45 days before the rows
    for (const bad of [patch("2026-10-20", "2026-10-31"), patch("2026-08-01", "2026-10-31")]) {
      expect(bad.body.detail).toMatch(/\.$/);
    }
    expect(route("PATCH", "batches/999/period", { period_start: "2026-10-01", period_end: "2026-10-31" }).status).toBe(404);
    const widened = patch("2026-10-01", "2026-10-31");
    expect(widened.status).toBe(200);
    expect(widened.body).toMatchObject({ period_start: "2026-10-01", period_end: "2026-10-31", can_widen: false });
  });

  it("review needs a well-formed month", () => {
    const every = route("GET", "review");
    expect([every.status, every.body.month, every.body.recognised]).toEqual([200, null, []]);
    expect(route("GET", "review?month=2026-13").status).toBe(422);
  });

  it("creates and edits accounts", () => {
    expect(route("POST", "accounts", { name: "Travel card", kind: "card" }).status).toBe(201);
    expect(route("POST", "accounts", { name: "Travel card", kind: "card" }).status).toBe(409);
    expect(ok("PATCH", "accounts/travel-card", { export_note: "Statements, then CSV" }).export_note)
      .toBe("Statements, then CSV");
  });

  it("a category of his own is trimmed and listed; a matching one keeps its spelling; bad names are 422", () => {
    const t = ok("GET", "review?month=2026-09").unplaced[0].charges[0];
    expect(ok("PUT", `transactions/${t.id}/override`, { category: "  Pottery " }).category).toBe("Pottery");
    expect(ok("GET", "categories").categories).toContain("Pottery");
    expect(ok("PUT", `transactions/${t.id}/override`, { category: "transport" }).category).toBe("Transport");
    expect(ok("GET", "categories").categories).not.toContain("Other");
    for (const bad of ["  ", "x".repeat(41), "a\tb", "UNCATEGORISED"]) {
      expect(route("PUT", `transactions/${t.id}/override`, { category: bad }).status).toBe(422);
      expect(route("POST", `transactions/${t.id}/merchant-rule`, { kind: "spending", category: bad }).status).toBe(422);
    }
  });
});
