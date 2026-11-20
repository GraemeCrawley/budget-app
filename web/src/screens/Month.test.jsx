import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { get } from "../api.js";
import Month from "./Month.jsx";

vi.mock("../api.js", () => ({ get: vi.fn() }));

const BLOCKS = { Food: 60000, Bills: 180000, Subscriptions: 3000, "Big purchases": 0, Buckets: 0,
  "Everything else": 20000 };

function month(ym, extra = {}) {
  return { month: ym, income_cents: 400000, spending_cents: 263000, saving_cents: 50000,
    savings_rate: 0.3425, blocks: BLOCKS, food_out_cents: 20000, food_home_cents: 40000,
    complete: true, provisional: false, one_off_income: false, uncategorised_count: 0,
    unconfirmed_income_count: 0, reviewed: true, changed_since_review: false, ...extra };
}

const ACCOUNTS = { accounts: [
  { key: "chequing", name: "Chequing", kind: "chequing", data_through: "2026-02-28",
    ranges: [["2025-11-01", "2026-02-28"]] },
  { key: "card", name: "Card", kind: "card", data_through: "2026-02-10",
    ranges: [["2025-11-01", "2026-02-10"]] },
] };

function answer(months, data_through = { chequing: "2026-02-28", card: "2026-02-10" }) {
  get.mockImplementation((path) => {
    if (path === "months") return Promise.resolve({ months, data_through });
    if (path === "accounts") return Promise.resolve(ACCOUNTS);
    if (path.startsWith("transactions?month=")) {
      return Promise.resolve({ transactions: path.endsWith("2026-01")
        ? [{ id: 1, date: "2026-01-03", amount_cents: -180000, block: "Bills" }] : [] });
    }
    return Promise.reject(new Error(`unexpected ${path}`));
  });
}

beforeEach(() => {
  get.mockReset();
  location.hash = "#/";
});

describe("Month", () => {
  it("shows the month's rate as the big number, with its name, and a way back to every month", async () => {
    answer([month("2025-12"), month("2026-01", { savings_rate: 0.2345 }),
      month("2026-02", { complete: false, savings_rate: 0.5 })]);
    render(<Month ym="2026-01" />);
    expect(await screen.findByText("23%")).toBeInTheDocument();
    expect(screen.getByText(/January 2026/)).toBeInTheDocument();
    expect(screen.getByText("Data through Feb 10")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "‹ Months" })).toHaveAttribute("href", "#/months");
  });

  it("has one chart: the month's spending as it built up day by day", async () => {
    answer([month("2025-12"), month("2026-01")]);
    render(<Month ym="2026-01" />);
    await screen.findByText("34%");
    expect(await screen.findByRole("img", { name: "Spending so far by day and group" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Spending by month and group" })).toBeNull();
    expect(get).toHaveBeenCalledWith("transactions?month=2025-12"); // the month before, to compare against
  });

  it("says plainly when a month is incomplete, and names the account that is behind", async () => {
    answer([month("2026-01"), month("2026-02", { complete: false })]);
    render(<Month ym="2026-02" />);
    expect(await screen.findByText("This month is incomplete")).toBeInTheDocument();
    expect(screen.getByText(/Card has data through Feb 10/)).toBeInTheDocument();
    expect(screen.queryByText(/Chequing has data/)).not.toBeInTheDocument();
  });

  it("states provisional and changed-since-review months", async () => {
    answer([month("2026-01", { provisional: true, changed_since_review: true })]);
    render(<Month ym="2026-01" />);
    expect(await screen.findByText("Includes charges not yet confirmed by a statement")).toBeInTheDocument();
    expect(screen.getByText("Totals changed since you reviewed this month")).toBeInTheDocument();
  });

  it("links the charges that need a look to that month's review", async () => {
    answer([month("2026-01", { uncategorised_count: 2, unconfirmed_income_count: 1 })]);
    render(<Month ym="2026-01" />);
    const link = await screen.findByRole("link", { name: "3 charges need a look" });
    expect(link).toHaveAttribute("href", "#/review/2026-01");
  });

  it("shows no review button when nothing needs a look", async () => {
    answer([month("2026-01")]);
    render(<Month ym="2026-01" />);
    await screen.findByText("34%");
    expect(screen.queryByText(/need a look/)).not.toBeInTheDocument();
  });

  it("shows income, spending and saved, and links each block to its detail", async () => {
    answer([month("2026-01")]);
    render(<Month ym="2026-01" />);
    const totals = within(await screen.findByRole("region", { name: "Totals" }));
    expect(totals.getByText("$4,000")).toBeInTheDocument();
    expect(totals.getByText("$2,630")).toBeInTheDocument();
    expect(totals.getByText("$1,370")).toBeInTheDocument();
    const bills = screen.getByRole("link", { name: /Bills/ });
    expect(bills).toHaveAttribute("href", "#/block/2026-01/Bills");
    expect(screen.getByRole("link", { name: /Everything else/ }))
      .toHaveAttribute("href", "#/block/2026-01/Everything%20else");
    expect(screen.queryByRole("link", { name: /Big purchases/ })).toBeNull(); // nothing spent, nothing usual: not listed
  });

  it("sets each group against its usual over the full months before, biggest gap first", async () => {
    const was = (blocks) => month("x", { blocks: { ...BLOCKS, ...blocks } });
    answer([{ ...was({ Food: 20000 }), month: "2025-11" }, { ...was({ Food: 40000, Bills: 181000 }), month: "2025-12" },
      month("2026-01")]);
    render(<Month ym="2026-01" />);
    const where = within(await screen.findByRole("region", { name: "Where it went" }));
    expect(where.getByText("Usual is your average over the 2 full months before, marked by the tick on each bar.")).toBeInTheDocument();
    const food = where.getAllByRole("link")[0];
    expect(food.querySelector(".usualbar .over")).not.toBeNull(); // Food ran past its usual
    expect(food.querySelector(".usualbar .tick").style.left).toBe(`${(30000 / 180500) * 100}%`);
    const rows = where.getAllByRole("link").map((a) => a.textContent);
    expect(rows[0]).toContain("Food");
    expect(rows[0]).toContain("$300 above usual");
    expect(rows.find((r) => r.startsWith("Bills"))).toContain("about usual");
  });

  it("the first month has no usual to compare with, and says nothing about it", async () => {
    answer([month("2026-01")]);
    render(<Month ym="2026-01" />);
    const where = within(await screen.findByRole("region", { name: "Where it went" }));
    expect(where.queryByText(/usual/)).toBeNull();
  });

  it("lists the month's biggest charges, each opening its charge", async () => {
    answer([month("2026-01")]);
    render(<Month ym="2026-01" />);
    const big = within(await screen.findByRole("region", { name: "Biggest charges" }));
    expect(big.getAllByRole("button")).toHaveLength(1);
    expect(big.getByText("-$1,800.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All purchases in January" })).toHaveAttribute("href", "#/charges/2026-01");
  });

  it("notes a one-off charge under the big number", async () => {
    answer([month("2025-12"), month("2026-01", { one_off_spending: true })]);
    render(<Month ym="2026-01" />);
    expect(await screen.findByText("Includes a one-off charge, so this month runs low.")).toBeInTheDocument();
  });

  it("notes a one-off deposit under the big number, only when the month has one", async () => {
    answer([month("2026-01", { one_off_income: true })]);
    const { unmount } = render(<Month ym="2026-01" />);
    expect(await screen.findByText("Includes a one-off deposit, so this month runs high.")).toBeInTheDocument();
    unmount();
    answer([month("2026-01")]);
    render(<Month ym="2026-01" />);
    await screen.findByText("34%");
    expect(screen.queryByText(/one-off deposit/)).not.toBeInTheDocument();
  });

  it("steps to the previous month with the arrow", async () => {
    answer([month("2025-12"), month("2026-01")]);
    render(<Month ym="2026-01" />);
    await userEvent.click(await screen.findByRole("link", { name: "Previous month" }));
    expect(location.hash).toBe("#/month/2025-12");
  });

  it("shows a plain problem with a retry when the request fails", async () => {
    get.mockRejectedValue(new Error("offline"));
    render(<Month ym="2026-01" />);
    expect(await screen.findByText("Couldn't load this. Try again.")).toBeInTheDocument();
    const calls = get.mock.calls.length;
    answer([month("2026-01")]);
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(get.mock.calls.length).toBeGreaterThan(calls);
    expect(await screen.findByText("34%")).toBeInTheDocument();
  });

  it("shows Loading and no figure while the request is out", () => {
    get.mockReturnValue(new Promise(() => {}));
    render(<Month ym="2026-01" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
  });

  it("shows a dash for a month with no rate", async () => {
    answer([month("2026-01", { income_cents: 0, savings_rate: null })]);
    render(<Month ym="2026-01" />);
    expect(await screen.findByText("–")).toHaveClass("big");
  });

  it("says there is nothing yet when there are no months", async () => {
    answer([], {});
    render(<Month ym="2026-01" />);
    expect(await screen.findByText("No months yet. Add a file to start.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add a file" })).toHaveAttribute("href", "#/add");
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("says plainly when the chosen month has no data", async () => {
    answer([month("2026-01")]);
    render(<Month ym="2026-03" />);
    expect(await screen.findByText("There is no data for March 2026.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See every month" })).toHaveAttribute("href", "#/months");
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });
});
