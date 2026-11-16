import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import MoneyChart, { moneyScale, shortDollars } from "./MoneyChart.jsx";

const m = (month, income_cents, spending_cents) => ({ month, income_cents, spending_cents });
const MONTHS = [m("2026-01", 620000, 409000), m("2026-02", 600000, 380000), m("2026-03", 640000, 450000)];

describe("MoneyChart", () => {
  it("draws one line for income and one for spending, and names them", () => {
    const { container } = render(<MoneyChart months={MONTHS} chosen="2026-03" />);
    expect(container.querySelectorAll(".recharts-line")).toHaveLength(2);
    expect(container.querySelector(".legend").textContent).toBe("Income$6,400Spending$4,500");
  });

  it("each other month is a link to that month", () => {
    const { container } = render(<MoneyChart months={MONTHS} chosen="2026-03" />);
    expect([...container.querySelectorAll("a")].map((a) => a.getAttribute("href")))
      .toEqual(["#/month/2026-01", "#/month/2026-02"]);
  });

  it("draws the chosen month's dots larger", () => {
    const { container } = render(<MoneyChart months={MONTHS} chosen="2026-03" />);
    const sizes = [...container.querySelectorAll("circle")].map((d) => d.getAttribute("r"));
    expect(sizes.filter((r) => r === "5")).toHaveLength(2);
    expect(sizes.filter((r) => r === "3")).toHaveLength(4);
  });

  it("starts the axis at zero and ends on a round number with few ticks", () => {
    expect(moneyScale([620000, 409000])).toEqual({ domain: [0, 8000], ticks: [0, 2000, 4000, 6000, 8000] });
    expect(moneyScale([90000, 40000])).toEqual({ domain: [0, 1000], ticks: [0, 500, 1000] });
    expect(moneyScale([])).toEqual({ domain: [0, 500], ticks: [0, 500] });
  });

  it("goes below zero when refunds outweigh a month's spending", () => {
    const { domain, ticks } = moneyScale([300000, -40000]);
    expect(domain).toEqual([-1000, 3000]);
    expect(ticks).toContain(0);
  });

  it("labels the axis in short dollars", () => {
    expect([0, 500, 2000, 2500, -1000].map(shortDollars)).toEqual(["$0", "$500", "$2k", "$2.5k", "-$1k"]);
  });
});
