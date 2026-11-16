import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { get } from "../api.js";
import Home from "./Home.jsx";

vi.mock("../api.js", () => ({ get: vi.fn() }));

function month(ym, income_cents, spending_cents, extra = {}) {
  return { month: ym, income_cents, spending_cents, savings_rate: (income_cents - spending_cents) / income_cents,
    blocks: { Food: spending_cents / 4, Bills: (spending_cents * 3) / 4, Buckets: 0 }, complete: true,
    uncategorised_count: 0, unconfirmed_income_count: 0, ...extra };
}
const MONTHS = [month("2026-01", 500000, 400000), month("2026-02", 400000, 300000),
  month("2026-03", 600000, 300000), month("2026-04", 500000, 200000),
  month("2026-05", 100000, 90000, { complete: false })];

function answer(months, data_through = { chequing: "2026-05-10" }) {
  get.mockImplementation((path) => (path === "months"
    ? Promise.resolve({ months, data_through }) : Promise.reject(new Error(`unexpected ${path}`))));
}

beforeEach(() => {
  get.mockReset();
});

describe("Home", () => {
  it("leads with the last full month's rate against the target, with the three-month figure beside it", async () => {
    answer(MONTHS);
    render(<Home />);
    expect(await screen.findByText("60%")).toBeInTheDocument();
    expect(document.querySelector(".hero .pill").textContent).toBe("April 2026");
    expect(screen.getByText("45 points above your 15% target")).toBeInTheDocument();
    expect(screen.getByText("Last 3 months: 47%")).toBeInTheDocument();
    const totals = screen.getByRole("link", { name: "April 2026 in full" });
    expect(totals).toHaveAttribute("href", "#/month/2026-04");
    expect(totals).toHaveTextContent("Income$5,000");
    expect(totals).toHaveTextContent("Spending$2,000");
    expect(totals).toHaveTextContent("Saved$3,000");
  });

  it("says when the rate is exactly on the target", async () => {
    answer([month("2026-01", 100000, 85000)]);
    render(<Home />);
    expect(await screen.findByText("On your 15% target")).toBeInTheDocument();
  });

  it("measures against the target set on the Plan screen", async () => {
    get.mockResolvedValue({ months: [month("2026-01", 100000, 85000)], data_through: {}, target: 0.2 });
    render(<Home />);
    expect(await screen.findByText("5 points below your 20% target")).toBeInTheDocument();
  });

  it("marks the headline month when no month is full yet", async () => {
    answer([month("2026-05", 100000, 90000, { complete: false })]);
    render(<Home />);
    expect(await screen.findByText("not a full month yet")).toBeInTheDocument();
  });

  it("charts only full months, and the charts are not links", async () => {
    answer(MONTHS);
    const { container } = render(<Home />);
    const chart = await screen.findByRole("img", { name: "Savings rate by month" });
    expect(chart.textContent).toContain("Apr");
    expect(chart.textContent).not.toContain("May");
    expect(screen.getByRole("img", { name: "Income and spending by month" })).toBeInTheDocument();
    expect(container.querySelectorAll(".chartlinks a")).toHaveLength(0);
  });

  it("shows what changed against the month before as figures, biggest move first", async () => {
    answer(MONTHS);
    render(<Home />);
    const region = await screen.findByRole("region", { name: "What changed" });
    expect(region).toHaveTextContent("against March");
    expect(within(region).getAllByRole("listitem").map((r) => r.textContent)).toEqual([
      "Incomedown $1,000", "Spendingdown $1,000", "Billsdown $750", "Fooddown $250"]);
  });

  it("leaves out what changed when there is no month before", async () => {
    answer(MONTHS.slice(3));
    render(<Home />);
    await screen.findByText("60%");
    expect(screen.queryByRole("region", { name: "What changed" })).toBeNull();
  });

  it("shows where the month went, largest first, each group opening its own page", async () => {
    answer(MONTHS);
    render(<Home />);
    const links = within(await screen.findByRole("region", { name: "Where it went" })).getAllByRole("link");
    expect(links.map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Bills$1,500", "#/block/2026-04/Bills"], ["Food$500", "#/block/2026-04/Food"]]);
  });

  it("offers one list for every charge waiting, whatever its month", async () => {
    answer([month("2026-01", 1, 1, { uncategorised_count: 2 }), ...MONTHS.slice(1, 4),
      month("2026-05", 1, 1, { complete: false, unconfirmed_income_count: 1 })]);
    render(<Home />);
    const link = within(await screen.findByRole("region", { name: "Waiting for you" })).getByRole("link");
    expect([link.textContent, link.getAttribute("href")]).toEqual(["3 charges to check", "#/review"]);
  });

  it("says nothing is waiting when nothing is", async () => {
    answer(MONTHS);
    render(<Home />);
    expect(await screen.findByText("Nothing. Every charge is checked.")).toBeInTheDocument();
  });

  it("links to every month and says how far the data goes", async () => {
    answer(MONTHS);
    render(<Home />);
    expect(await screen.findByRole("link", { name: "See every month" })).toHaveAttribute("href", "#/months");
    expect(screen.getByText("Data through May 10")).toBeInTheDocument();
  });

  it("words a month that lost money plainly, and says how far under the target it is", async () => {
    answer([month("2026-01", 100000, 110000), month("2026-02", 100000, 110000)]);
    render(<Home />);
    expect(await screen.findByText("You spent more than came in.")).toBeInTheDocument();
    expect(screen.getByText("25 points below your 15% target")).toBeInTheDocument();
  });

  it("says there is nothing yet when there are no months", async () => {
    answer([]);
    render(<Home />);
    expect(await screen.findByText("No months yet. Add a file to start.")).toBeInTheDocument();
  });

  it("shows a plain problem when the request fails", async () => {
    get.mockRejectedValue(Object.assign(new Error("x"), { status: 500, detail: "boom" }));
    render(<Home />);
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
