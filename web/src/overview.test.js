import { describe, expect, it } from "vitest";
import { againstUsual, needingALook, pooled, recent, usualBlocks } from "./overview.js";

const m = (month, income_cents, spending_cents, extra = {}) => ({ month, income_cents, spending_cents, complete: true,
  blocks: { Food: spending_cents / 2, Bills: spending_cents / 2 }, uncategorised_count: 0, unconfirmed_income_count: 0,
  ...extra });
const MONTHS = [m("2026-01", 500000, 400000), m("2026-02", 400000, 300000), m("2026-03", 600000, 300000),
  m("2026-04", 500000, 200000), m("2026-05", 100000, 90000, { complete: false })];

describe("recent", () => {
  it("is the latest full months, oldest first, never a month still being filled in", () => {
    expect(recent(MONTHS, 3).map((x) => x.month)).toEqual(["2026-02", "2026-03", "2026-04"]);
    expect(recent(MONTHS, 12)).toHaveLength(4);
  });

  it("falls back to every month when none is full", () => {
    expect(recent([MONTHS[4]], 3)).toEqual([MONTHS[4]]);
  });
});

describe("pooled", () => {
  it("is what was kept of everything that came in, and the monthly averages", () => {
    expect(pooled(recent(MONTHS, 3))).toEqual({ count: 3, rate: 700000 / 1500000, income_cents: 500000,
      spending_cents: 266667, saved_cents: 233333 });
  });

  it("has no rate when nothing came in, and is null with no months", () => {
    expect(pooled([m("2026-01", 0, 5000)]).rate).toBeNull();
    expect(pooled([])).toBeNull();
  });
});

describe("usualBlocks", () => {
  it("averages each group over the months, largest first, with the average of the months before", () => {
    expect(usualBlocks(recent(MONTHS, 2), [MONTHS[0], MONTHS[1]])).toEqual([
      { name: "Bills", cents: 125000, before_cents: 175000 }, { name: "Food", cents: 125000, before_cents: 175000 }]);
  });

  it("has no earlier figure when there are no months before", () => {
    expect(usualBlocks([MONTHS[0]], [])[0].before_cents).toBeNull();
  });
});

describe("needingALook", () => {
  it("lists the months with charges to look at, newest first, with how many", () => {
    const months = [m("2026-01", 1, 1, { uncategorised_count: 2 }), m("2026-02", 1, 1),
      m("2026-03", 1, 1, { uncategorised_count: 1, unconfirmed_income_count: 3 })];
    expect(needingALook(months)).toEqual([{ month: "2026-03", count: 4 }, { month: "2026-01", count: 2 }]);
  });
});

describe("againstUsual", () => {
  const month = (blocks) => ({ blocks });
  it("sets each group beside its average over the earlier months, biggest gap first", () => {
    const rows = againstUsual(month({ Food: 90000, Bills: 180000, Fun: 1000 }),
      [month({ Food: 50000, Bills: 180000 }), month({ Food: 70000, Bills: 170000, Travel: 30000 })]);
    expect(rows).toEqual([
      { name: "Food", cents: 90000, usual_cents: 60000, gap_cents: 30000 },
      { name: "Travel", cents: 0, usual_cents: 15000, gap_cents: -15000 },
      { name: "Bills", cents: 180000, usual_cents: 175000, gap_cents: 5000 },
      { name: "Fun", cents: 1000, usual_cents: 0, gap_cents: 1000 }]);
  });
  it("with nothing earlier, lists the groups by size with no usual figure", () => {
    expect(againstUsual(month({ Food: 1, Bills: 5, Buckets: 0 }), [])).toEqual([
      { name: "Bills", cents: 5, usual_cents: null, gap_cents: null }, { name: "Food", cents: 1, usual_cents: null, gap_cents: null }]);
  });
});
