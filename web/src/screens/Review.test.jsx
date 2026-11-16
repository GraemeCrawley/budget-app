import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { get, send } from "../api.js";
import Review from "./Review.jsx";

vi.mock("../api.js", () => ({ get: vi.fn(), send: vi.fn() }));

const CATEGORIES = { categories: ["Can't remember", "Coffee", "Groceries", "Gifts"],
  blocks: { "Can't remember": "Everything else", Coffee: "Food", Groceries: "Food", Gifts: "Everything else" } };

function tx(id, extra = {}) {
  return { id, date: "2026-01-14", amount_cents: -1234, description: "SOME SHOP 12", account: "card", account_name: "Card",
    kind: "spending", category: "Uncategorised", block: "Everything else", one_off: false, provisional: false,
    why: "no rule matched", guessed: false, merchant: "", ...extra };
}

const REVIEW = {
  month: "2026-01", reviewed: false,
  unplaced: [
    { merchant: "CORNER CAFE", count: 2, cents: 2468, charges: [tx(21, { merchant: "CORNER CAFE", description: "CORNER CAFE 1" }), tx(22, { merchant: "CORNER CAFE", description: "CORNER CAFE 2" })] },
    { merchant: "", count: 2, cents: 1000, charges: [tx(31, { description: "MYSTERY ONE", amount_cents: -600 }), tx(32, { description: "MYSTERY TWO", amount_cents: -400 })] },
  ],
  unconfirmed_income: [tx(41, { kind: "income", category: "", guessed: true, amount_cents: 50000, description: "NORTHWIND PAYROLL", merchant: "NORTHWIND" })],
  recognised: [{ category: "Groceries", block: "Food", cents: 4500, charges: [
    tx(51, { category: "Groceries", merchant: "GREEN GROCER", description: "GREEN GROCER 1", first_time: true, amount_cents: -3000 }),
    tx(52, { category: "Groceries", merchant: "FARM STAND", description: "FARM STAND 2", first_time: false, amount_cents: -1500 })] }],
};

let current;
function show(review = REVIEW) {
  current = review;
  get.mockImplementation((path) => {
    if (path === "review?month=2026-01") return Promise.resolve(current);
    if (path === "categories") return Promise.resolve(CATEGORIES);
    return Promise.reject(new Error(`unexpected ${path}`));
  });
}

beforeEach(() => {
  get.mockReset();
  send.mockReset();
  location.hash = "#/review/2026-01";
});

describe("Review", () => {
  it("'2 to place' shows the merchant groups in the order the server sends them, with count and total", async () => {
    show();
    render(<Review ym="2026-01" />);
    expect(await screen.findByRole("heading", { name: "2 to place" })).toBeInTheDocument();
    const groups = screen.getAllByTestId("group");
    expect(within(groups[0]).getByText("CORNER CAFE")).toBeInTheDocument();
    expect(within(groups[0]).getByText("2 charges, $24.68")).toBeInTheDocument();
    expect(within(groups[1]).getByText("No merchant")).toBeInTheDocument();
  });

  it("picking Coffee for CORNER CAFE posts the merchant rule from its first charge and the group leaves the list", async () => {
    show();
    send.mockImplementation(async () => {
      current = { ...REVIEW, unplaced: [REVIEW.unplaced[1]] };
      return { merchant: "CORNER CAFE", charges: 2 };
    });
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    await user.click(await screen.findByRole("button", { name: "Choose a category for CORNER CAFE" }));
    await user.click(await screen.findByRole("button", { name: /^Coffee/ }));
    expect(send).toHaveBeenCalledWith("POST", "transactions/21/merchant-rule", { kind: "spending", category: "Coffee" });
    expect(await screen.findByRole("heading", { name: "1 to place" })).toBeInTheDocument();
    expect(screen.queryByText("CORNER CAFE")).not.toBeInTheDocument();
  });

  it("a group can be expanded to its charges, which open the charge view", async () => {
    show();
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    await user.click(await screen.findByRole("button", { name: "Show the charges from CORNER CAFE" }));
    const rows = screen.getAllByRole("button", { name: /\$12\.34/ });
    expect(rows).toHaveLength(2);
    await user.click(rows[1]);
    expect(location.hash).toBe("#/charge/22");
  });

  it("a group with no merchant shows its charges, each set on its own with an override", async () => {
    show();
    send.mockResolvedValue(tx(32, { category: "Gifts" }));
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    await screen.findByText("MYSTERY TWO");
    expect(screen.getByText("MYSTERY ONE")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Choose a category for No merchant" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Choose a category for MYSTERY TWO" }));
    await user.click(await screen.findByRole("button", { name: /^Gifts/ }));
    expect(send).toHaveBeenCalledWith("PUT", "transactions/32/override", { category: "Gifts" });
  });

  it("a failed placement says so, keeps the list, and Try again resends the same call", async () => {
    show();
    send.mockRejectedValueOnce(Object.assign(new Error("net"), { status: 502 }));
    send.mockResolvedValueOnce({ merchant: "CORNER CAFE", charges: 2 });
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    await user.click(await screen.findByRole("button", { name: "Choose a category for CORNER CAFE" }));
    await user.click(await screen.findByRole("button", { name: /^Coffee/ }));
    expect(await screen.findByText("Couldn't save that. Try again.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2 to place" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[1]).toEqual(send.mock.calls[0]);
    expect(screen.queryByText("Couldn't save that. Try again.")).not.toBeInTheDocument();
  });

  it("'Yes, income' sends PUT override {kind: income}; 'No' sends {kind: transfer}", async () => {
    show({ ...REVIEW, unconfirmed_income: [REVIEW.unconfirmed_income[0], tx(42, { kind: "income", guessed: true, description: "ODD DEPOSIT" })] });
    send.mockResolvedValue({});
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    expect(await screen.findByRole("heading", { name: "Is this income?" })).toBeInTheDocument();
    const rows = screen.getAllByTestId("income-row");
    await user.click(within(rows[0]).getByRole("button", { name: "Yes, income" }));
    expect(send).toHaveBeenCalledWith("PUT", "transactions/41/override", { kind: "income" });
    await user.click(within(rows[1]).getByRole("button", { name: "No" }));
    expect(send).toHaveBeenCalledWith("PUT", "transactions/42/override", { kind: "transfer" });
  });

  it("an income row links to its charge view for anything else", async () => {
    show();
    render(<Review ym="2026-01" />);
    expect(await screen.findByRole("link", { name: "Something else" })).toHaveAttribute("href", "#/charge/41");
  });

  it("Recognised is collapsed; opening a category lists its charges with first-time merchants marked new", async () => {
    show();
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    expect(screen.queryByText("Groceries")).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /^Recognised/ }));
    await user.click(screen.getByRole("button", { name: /^Groceries/ }));
    const rows = screen.getAllByRole("button", { name: /GREEN GROCER|FARM STAND/ });
    expect(within(rows[0]).getByText(/new/)).toBeInTheDocument();
    expect(within(rows[1]).queryByText(/new/)).not.toBeInTheDocument();
    await user.click(rows[1]);
    expect(location.hash).toBe("#/charge/52");
  });

  it("'Done reviewing' posts months/2026-01/reviewed and goes to the month just reviewed", async () => {
    show();
    send.mockResolvedValue({ month: "2026-01", reviewed: true });
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    await user.click(await screen.findByRole("button", { name: "Done reviewing" }));
    expect(send).toHaveBeenCalledWith("POST", "months/2026-01/reviewed");
    await vi.waitFor(() => expect(location.hash).toBe("#/month/2026-01"));
  });

  it("a merchant with charges and refunds is two groups, and each posts the rule from its own first charge", async () => {
    const refund = tx(23, { merchant: "CORNER CAFE", description: "CORNER CAFE REFUND", amount_cents: 500 });
    show({ ...REVIEW, unplaced: [REVIEW.unplaced[0], { merchant: "CORNER CAFE", count: 1, cents: -500, charges: [refund] }] });
    send.mockResolvedValue({ merchant: "CORNER CAFE", charges: 1 });
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    const groups = await screen.findAllByTestId("group");
    expect(groups).toHaveLength(2);
    await user.click(within(groups[1]).getByRole("button", { name: "Choose a category for CORNER CAFE" }));
    await user.click(await screen.findByRole("button", { name: /^Coffee/ }));
    await vi.waitFor(() => expect(send).toHaveBeenCalledWith("POST", "transactions/23/merchant-rule",
      { kind: "spending", category: "Coffee" }));
    expect(errors.mock.calls.filter((c) => String(c[0]).includes("same key"))).toEqual([]);
    errors.mockRestore();
  });

  it("a failed Done stays on the screen and Try again resends it", async () => {
    show();
    send.mockRejectedValueOnce(Object.assign(new Error("net"), { status: 502 }));
    send.mockResolvedValueOnce({});
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    await user.click(await screen.findByRole("button", { name: "Done reviewing" }));
    expect(await screen.findByText("Couldn't save that. Try again.")).toBeInTheDocument();
    expect(location.hash).toBe("#/review/2026-01");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await vi.waitFor(() => expect(location.hash).toBe("#/month/2026-01"));
  });

  it("an empty review shows 'Nothing needs placing' with the recognised list and the Done button", async () => {
    show({ ...REVIEW, unplaced: [], unconfirmed_income: [] });
    render(<Review ym="2026-01" />);
    expect(await screen.findByText("Nothing needs placing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Groceries/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done reviewing" })).toBeInTheDocument();
    expect(screen.queryByText(/to place$/)).not.toBeInTheDocument();
  });

  it("a failed load says so with a retry", async () => {
    get.mockRejectedValueOnce(Object.assign(new Error("net"), { status: 502 }));
    get.mockResolvedValue(REVIEW);
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "2 to place" })).toBeInTheDocument();
  });
  it("a failed reload after a saved answer is not called a failed save, and Retry only reloads", async () => {
    let calls = 0;
    get.mockImplementation((path) => {
      if (path === "categories") return Promise.resolve(CATEGORIES);
      calls += 1;
      if (calls === 2) return Promise.reject(Object.assign(new Error("net"), { status: 502 }));
      return Promise.resolve(calls === 1 ? REVIEW : { ...REVIEW, unplaced: [REVIEW.unplaced[1]] });
    });
    send.mockResolvedValue({ merchant: "CORNER CAFE", charges: 2 });
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    await user.click(await screen.findByRole("button", { name: "Choose a category for CORNER CAFE" }));
    await user.click(await screen.findByRole("button", { name: /^Coffee/ }));
    expect(await screen.findByText("Saved, but couldn't reload.")).toBeInTheDocument();
    expect(screen.queryByText("Couldn't save that. Try again.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "1 to place" })).toBeInTheDocument();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("with no month, lists every month's charges in one place and has no 'Done reviewing'", async () => {
    get.mockImplementation((path) => (path === "review"
      ? Promise.resolve({ ...REVIEW, month: null, recognised: [] }) : Promise.reject(new Error(`unexpected ${path}`))));
    render(<Review />);
    expect(await screen.findByRole("heading", { name: "Charges to check" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Done reviewing" })).toBeNull();
    expect(screen.getByRole("link", { name: "Finish later" })).toHaveAttribute("href", "#/");
  });

  it("picking the Can't remember category files each of a shop's charges without making a rule for the shop", async () => {
    show();
    send.mockImplementation(async () => { current = { ...REVIEW, unplaced: [REVIEW.unplaced[1]] }; return {}; });
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    await user.click(await screen.findByRole("button", { name: "Choose a category for CORNER CAFE" }));
    await user.click(await within(await screen.findByRole("dialog")).findByRole("button", { name: /^Can't remember/ }));
    expect(send.mock.calls).toEqual([
      ["PUT", "transactions/21/override", { kind: "spending", category: "Can't remember" }],
      ["PUT", "transactions/22/override", { kind: "spending", category: "Can't remember" }]]);
    expect(await screen.findByRole("heading", { name: "1 to place" })).toBeInTheDocument();
  });

  it("with no month, one button files every old, small charge as can't remember and leaves the rest", async () => {
    vi.useFakeTimers({ now: new Date("2026-11-15T12:00:00"), toFake: ["Date"] });
    const old = (id, extra) => tx(id, { date: "2026-03-01", merchant: "OLD SHOP", ...extra });
    const all = { ...REVIEW, month: null, recognised: [], unconfirmed_income: [], unplaced: [
      { merchant: "OLD SHOP", count: 2, cents: 2468, charges: [old(61), old(62)] },
      { merchant: "OLD BIG", count: 1, cents: 90000, charges: [old(63, { merchant: "OLD BIG", amount_cents: -90000 })] },
      { merchant: "NEW SHOP", count: 1, cents: 1234, charges: [tx(64, { date: "2026-10-20", merchant: "NEW SHOP" })] },
      { merchant: "OLD REFUND", count: 1, cents: -500, charges: [old(65, { merchant: "OLD REFUND", amount_cents: 500 })] },
    ] };
    get.mockImplementation((path) => (path === "review" ? Promise.resolve(all) : Promise.reject(new Error(path))));
    send.mockResolvedValue({});
    const user = userEvent.setup();
    render(<Review />);
    await user.click(await screen.findByRole("button", { name: "Can't remember the 3 old, small ones" }));
    expect(send.mock.calls.map((c) => c[1])).toEqual(
      ["transactions/61/override", "transactions/62/override", "transactions/65/override"]);
    vi.useRealTimers();
  });

  it("a month's own review has no button for old charges", async () => {
    show();
    render(<Review ym="2026-01" />);
    await screen.findByRole("heading", { name: "2 to place" });
    expect(screen.queryByRole("button", { name: /old, small/ })).toBeNull();
  });

  it("the Can't remember button on a shop files each of its charges without making a rule", async () => {
    show();
    send.mockImplementation(async () => { current = { ...REVIEW, unplaced: [REVIEW.unplaced[1]] }; return {}; });
    const user = userEvent.setup();
    render(<Review ym="2026-01" />);
    await user.click(await screen.findByRole("button", { name: "Can't remember what CORNER CAFE was" }));
    expect(send.mock.calls.map((c) => c[1])).toEqual(["transactions/21/override", "transactions/22/override"]);
    expect(await screen.findByRole("heading", { name: "1 to place" })).toBeInTheDocument();
  });
});
