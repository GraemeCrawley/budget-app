import { describe, expect, it } from "vitest";
import { dailyByGroup, daysIn } from "./daily.js";

const t = (date, amount_cents, block) => ({ date, amount_cents, block });

describe("dailyByGroup", () => {
  it("knows how long a month is", () => {
    expect([daysIn("2026-02"), daysIn("2024-02"), daysIn("2026-10")]).toEqual([28, 29, 31]);
  });

  it("adds each day's spending to its group's running figure, one row per day", () => {
    const { groups, days } = dailyByGroup([
      t("2026-02-01", -150000, "Bills"), t("2026-02-03", -2000, "Food"), t("2026-02-03", -3000, "Food"),
      t("2026-02-20", -1000, "Bills")], "2026-02");
    expect(groups).toEqual(["Bills", "Food"]);
    expect(days).toHaveLength(28);
    expect(days[0]).toEqual({ day: 1, date: "2026-02-01", total: 150000, Bills: 150000, Food: 0 });
    expect(days[2]).toMatchObject({ Bills: 150000, Food: 5000, total: 155000 });
    expect(days[27]).toMatchObject({ Bills: 151000, Food: 5000, total: 156000 });
  });

  it("leaves out income and transfers (no group) and other months", () => {
    const { days } = dailyByGroup([
      t("2026-02-02", 400000, null), t("2026-01-31", -9900, "Food"), t("2026-02-02", -500, "Food")], "2026-02");
    expect(days[27].total).toBe(500);
  });

  it("a refund lowers its group but never below zero", () => {
    const { days } = dailyByGroup([t("2026-02-02", 2000, "Food"), t("2026-02-05", -5000, "Food")], "2026-02");
    expect(days[1].Food).toBe(0);
    expect(days[4].Food).toBe(3000);
  });

  it("a month still under way stops at the given day", () => {
    expect(dailyByGroup([t("2026-02-02", -500, "Food")], "2026-02", "2026-02-10").days).toHaveLength(10);
    expect(dailyByGroup([t("2026-02-02", -500, "Food")], "2026-02", "2026-03-10").days).toHaveLength(28);
  });
});
