import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { get } from "../api.js";
import Budgets from "./Budgets.jsx";

vi.mock("../api.js", () => ({ get: vi.fn() }));

const MONTHS = [
  { month: "2026-01", categories: { Food: { Groceries: 30000 }, "Everything else": { Travel: 90000 } } },
  { month: "2026-02", categories: { Food: { Groceries: 50000 }, "Big purchases": { Travel: 40000 } } },
];

beforeEach(() => get.mockReset());

describe("Budgets on a month's page", () => {
  it("sets each budget against the month, or the year so far, furthest over first", async () => {
    get.mockResolvedValue({ target: 0.15, budgets: [
      { category: "Groceries", cents: 60000, period: "month" }, { category: "Travel", cents: 100000, period: "year" }] });
    render(<Budgets months={MONTHS} ym="2026-02" />);
    const rows = within(await screen.findByRole("region", { name: "Budgets" })).getAllByRole("listitem");
    expect(rows.map((li) => li.textContent)).toEqual([
      "Travel$1,300 of $1,000this year so far$300 over", "Groceries$500 of $600this month$100 left"]);
    expect(screen.getByRole("link", { name: "Change" })).toHaveAttribute("href", "#/plan");
  });

  it("is left out when there are no budgets, or the plan cannot be read", async () => {
    get.mockResolvedValueOnce({ target: 0.15, budgets: [] }).mockRejectedValueOnce(new Error("x"));
    const first = render(<Budgets months={MONTHS} ym="2026-02" />);
    await Promise.resolve();
    expect(first.container).toBeEmptyDOMElement();
    const second = render(<Budgets months={MONTHS} ym="2026-02" />);
    await Promise.resolve();
    expect(second.container).toBeEmptyDOMElement();
  });
});
