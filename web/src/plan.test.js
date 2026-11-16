import { describe, expect, it } from "vitest";
import { budgetRows, spentByCategory, usualByCategory } from "./plan.js";

const month = (ym, categories, complete = true) => ({ month: ym, complete, categories });
const MONTHS = [
  month("2025-12", { Food: { Groceries: 90000 } }),
  month("2026-01", { Food: { Groceries: 30000, Coffee: 3000 }, "Everything else": { Travel: 10000 } }),
  month("2026-02", { Food: { Groceries: 50000 }, "Big purchases": { Travel: 70000 } }),
  month("2026-03", { Food: { Groceries: 10000 } }, false),
];

describe("budgets", () => {
  it("adds a category up across the groups its charges fell in", () => {
    expect(spentByCategory({ categories: { "Everything else": { Travel: 100 }, "Big purchases": { Travel: 900 } } }))
      .toEqual({ Travel: 1000 });
    expect(spentByCategory(undefined)).toEqual({});
  });

  it("usual is the average over the last three full months", () => {
    expect(usualByCategory(MONTHS)).toEqual({ Groceries: 56667, Coffee: 1000, Travel: 26667 });
  });

  it("sets a monthly budget against the month and a yearly one against the year so far, furthest over first", () => {
    const rows = budgetRows([
      { category: "Groceries", cents: 60000, period: "month" },
      { category: "Travel", cents: 60000, period: "year" },
      { category: "Coffee", cents: 5000, period: "month" },
    ], MONTHS, "2026-02");
    expect(rows.map((r) => [r.category, r.spent_cents, r.left_cents])).toEqual([
      ["Travel", 80000, -20000], ["Groceries", 50000, 10000], ["Coffee", 0, 5000]]);
  });
});
