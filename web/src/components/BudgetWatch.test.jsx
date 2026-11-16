import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { get } from "../api.js";
import BudgetWatch from "./BudgetWatch.jsx";

vi.mock("../api.js", () => ({ get: vi.fn() }));

const MONTHS = [
  { month: "2026-01", complete: true, categories: { Food: { Groceries: 30000 }, "Everything else": { Travel: 90000 } } },
  { month: "2026-02", complete: false, categories: { Food: { Groceries: 70000, Coffee: 2000 }, "Big purchases": { Travel: 40000 } } },
];
const plan = (budgets) => get.mockResolvedValue({ target: 0.15, budgets });

beforeEach(() => get.mockReset());

describe("Home's budget line", () => {
  it("names the budgets that have run over in the latest month, and by how much", async () => {
    plan([{ category: "Groceries", cents: 60000, period: "month" }, { category: "Coffee", cents: 5000, period: "month" },
      { category: "Travel", cents: 100000, period: "year" }]);
    render(<BudgetWatch months={MONTHS} />);
    const region = await screen.findByRole("region", { name: "Budgets" });
    expect(region).toHaveTextContent("2 of 3 over in February so far.");
    expect(within(region).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Travel (this year)$300 over", "Groceries$100 over"]);
    expect(within(region).getByRole("link", { name: "February in full" })).toHaveAttribute("href", "#/month/2026-02");
  });

  it("says so when every budget is on track", async () => {
    plan([{ category: "Coffee", cents: 5000, period: "month" }, { category: "Groceries", cents: 90000, period: "month" }]);
    render(<BudgetWatch months={MONTHS} />);
    expect(await screen.findByText("All 2 budgets are on track in February.")).toBeInTheDocument();
  });

  it("is left out when there are no budgets", async () => {
    plan([]);
    const { container } = render(<BudgetWatch months={MONTHS} />);
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });
});
