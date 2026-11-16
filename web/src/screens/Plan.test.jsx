import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { get, send } from "../api.js";
import Plan from "./Plan.jsx";

vi.mock("../api.js", () => ({ get: vi.fn(), send: vi.fn() }));

const month = (ym, groceries, coffee) => ({ month: ym, complete: true, income_cents: 500000, spending_cents: 400000,
  categories: { Food: { Groceries: groceries, Coffee: coffee } } });

function answer(plan = { target: 0.15, budgets: [{ category: "Coffee", cents: 6000, period: "month" }] }) {
  get.mockImplementation((path) => Promise.resolve({
    months: { months: [month("2026-01", 40000, 3000), month("2026-02", 60000, 5000)], data_through: {}, target: plan.target },
    plan,
    categories: { categories: ["Coffee", "Groceries", "Travel", "Uncategorised"], blocks: {} },
  }[path]));
}

beforeEach(() => {
  get.mockReset();
  send.mockReset();
});

describe("Plan", () => {
  it("raises and lowers the savings target a point at a time", async () => {
    answer();
    send.mockResolvedValue({ target: 0.16, budgets: [] });
    render(<Plan />);
    const target = await screen.findByRole("region", { name: "Savings target" });
    expect(within(target).getByText("15%")).toBeInTheDocument();
    expect(within(target).getByText("Your last 2 full months: 20%.")).toBeInTheDocument();
    expect(target).toHaveTextContent("About $750 a month, on your average income of $5,000.");
    await userEvent.click(within(target).getByRole("button", { name: "Raise the target" }));
    expect(send).toHaveBeenCalledWith("PUT", "plan/target", { target: 0.16 });
    expect(await within(target).findByText("16%")).toBeInTheDocument();
  });

  it("lists categories with their usual, budgeted ones first, and leaves out Uncategorised", async () => {
    answer();
    render(<Plan />);
    const budgets = await screen.findByRole("region", { name: "Budgets" });
    expect(within(budgets).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Coffee usually $40 a month, 1% of income$60 a month1% of income",
      "Groceries usually $500 a month, 10% of incomeNo budget", "Travel nothing latelyNo budget"]);
  });

  it("gives a category a yearly budget", async () => {
    answer();
    send.mockResolvedValue({ target: 0.15, budgets: [{ category: "Travel", cents: 300000, period: "year" }] });
    render(<Plan />);
    await userEvent.click(await screen.findByRole("button", { name: /^Travel/ }));
    const save = screen.getByRole("button", { name: "Save budget" });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Budget for Travel, in dollars"), "3000");
    await userEvent.click(screen.getByRole("button", { name: "A year" }));
    await userEvent.click(save);
    expect(send).toHaveBeenCalledWith("PUT", "plan/budgets", { category: "Travel", cents: 300000, period: "year" });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved the budget for Travel.");
    expect(screen.getByRole("button", { name: /^Travel/ })).toHaveTextContent("$3,000 a year5% of income");
  });

  it("fills in the usual amount for a category with no budget, ready to save", async () => {
    answer();
    send.mockResolvedValue({ target: 0.15, budgets: [] });
    render(<Plan />);
    await userEvent.click(await screen.findByRole("button", { name: /^Groceries/ }));
    expect(screen.getByLabelText("Budget for Groceries, in dollars")).toHaveValue("500");
    await userEvent.click(screen.getByRole("button", { name: "Save budget" }));
    expect(send).toHaveBeenCalledWith("PUT", "plan/budgets", { category: "Groceries", cents: 50000, period: "month" });
  });

  it("removes a budget", async () => {
    answer();
    send.mockResolvedValue({ target: 0.15, budgets: [] });
    render(<Plan />);
    await userEvent.click(await screen.findByRole("button", { name: /^Coffee/ }));
    expect(screen.getByLabelText("Budget for Coffee, in dollars")).toHaveValue("60");
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(send).toHaveBeenCalledWith("DELETE", "plan/budgets", { category: "Coffee" });
  });

  it("says so when a change does not save", async () => {
    answer();
    send.mockRejectedValue(Object.assign(new Error("x"), { detail: "the ledger is busy; try again in a moment" }));
    render(<Plan />);
    await userEvent.click(await screen.findByRole("button", { name: "Lower the target" }));
    expect(await screen.findByRole("status")).toHaveTextContent("the ledger is busy");
  });
});
