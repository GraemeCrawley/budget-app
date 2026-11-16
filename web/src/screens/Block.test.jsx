import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { get } from "../api.js";
import Block, { forgetPicked } from "./Block.jsx";

vi.mock("../api.js", () => ({ get: vi.fn() }));

function month(ym, food) {
  return { month: ym, income_cents: 400000, spending_cents: 100000, saving_cents: 0, savings_rate: 0.3,
    categories: { Food: { Groceries: food - 3000, Coffee: 2000, Other: 1000 }, Bills: { Rent: 180000 } },
    blocks: { Food: food, Bills: 180000, Subscriptions: 3000, "Big purchases": 0, Buckets: 0, "Everything else": 2000 },
    food_out_cents: 3000, food_home_cents: 9000, complete: true, provisional: false, one_off_income: false,
    uncategorised_count: 0, unconfirmed_income_count: 0, reviewed: true, changed_since_review: false };
}

function tx(id, date, cents, merchant, description, extra = {}) {
  return { id, date, amount_cents: cents, description, account: "card", account_name: "Card", kind: "spending",
    category: "Coffee", block: "Food", one_off: false, provisional: false, why: "rule: coffee", guessed: false,
    merchant, ...extra };
}

const CHARGES = [
  tx(1, "2026-02-03", -650, "CORNER CAFE", "CORNER CAFE 0412"),
  tx(2, "2026-02-20", -9000, "GREEN GROCER", "GREEN GROCER 114", { category: "Groceries" }),
  tx(3, "2026-02-10", -650, "CORNER CAFE", "CORNER CAFE 0412"),
  tx(4, "2026-02-15", -1200, "", "CASH WITHDRAWAL", { category: "Other" }),
  tx(5, "2026-02-25", -300, "BAKERY ONE", "BAKERY ONE", { provisional: true }),
  tx(6, "2026-02-26", -200, "BAKERY TWO", "BAKERY TWO"),
  tx(7, "2026-02-27", -100, "BAKERY THREE", "BAKERY THREE"),
];

function answer(charges = CHARGES) {
  get.mockImplementation((path) => {
    if (path === "months") {
      return Promise.resolve({ months: [month("2026-01", 11000), month("2026-02", 12000)], data_through: {} });
    }
    if (path.startsWith("transactions?")) return Promise.resolve({ transactions: charges });
    return Promise.reject(new Error(`unexpected ${path}`));
  });
}

beforeEach(() => {
  get.mockReset();
  forgetPicked();
  location.hash = "#/";
});

describe("Block", () => {
  it("asks for the month's charges in this block", async () => {
    answer();
    render(<Block ym="2026-02" block="Food" />);
    await screen.findByText("Eating out");
    expect(get).toHaveBeenCalledWith("transactions?month=2026-02&block=Food");
  });

  it("each other month in the chart is a link to this block in that month", async () => {
    answer();
    render(<Block ym="2026-02" block="Food" />);
    const link = await screen.findByRole("link", { name: "Food in January 2026" });
    expect(link).toHaveAttribute("href", "#/block/2026-01/Food");
    expect(screen.queryByRole("link", { name: "Food in February 2026" })).toBeNull();
  });

  it("a month with nothing in this block is not a link", async () => {
    get.mockImplementation((path) => {
      if (path === "months") {
        const empty = month("2026-01", 0);
        delete empty.blocks.Food;
        return Promise.resolve({ months: [empty, month("2026-02", 12000)], data_through: {} });
      }
      return Promise.resolve({ transactions: CHARGES });
    });
    render(<Block ym="2026-02" block="Food" />);
    await screen.findByText("Eating out");
    expect(screen.queryByRole("link", { name: /^Food in/ })).toBeNull();
  });

  it("Food shows eating out and eating at home side by side", async () => {
    answer();
    render(<Block ym="2026-02" block="Food" />);
    const out = (await screen.findByText("Eating out")).parentElement;
    expect(within(out).getByText("$30")).toBeInTheDocument();
    const home = screen.getByText("Eating at home").parentElement;
    expect(within(home).getByText("$90")).toBeInTheDocument();
  });

  it("picking a category shows it across the months, its amount and only its charges", async () => {
    answer();
    render(<Block ym="2026-02" block="Food" />);
    const show = await screen.findByRole("group", { name: "Show" });
    expect(within(show).getAllByRole("button").map((b) => b.textContent)).toEqual(["All", "Groceries", "Coffee", "Other"]);
    expect(screen.getByRole("img", { name: "Food by month" })).toBeInTheDocument();
    await userEvent.click(within(show).getByRole("button", { name: "Coffee" }));
    expect(screen.getByRole("img", { name: "Coffee by month" })).toBeInTheDocument();
    expect(screen.getByText("Coffee, February 2026")).toBeInTheDocument();
    expect(document.querySelector("h1 + .figure").textContent).toBe("$20");
    expect(screen.queryByText("Eating out")).not.toBeInTheDocument();
    const charges = screen.getByRole("region", { name: "Charges" });
    expect(within(charges).queryByText(/GREEN GROCER/)).not.toBeInTheDocument();
    expect(within(charges).getAllByText(/CORNER CAFE/).length).toBe(2);
    await userEvent.click(within(show).getByRole("button", { name: "All" }));
    expect(within(screen.getByRole("region", { name: "Charges" })).getByText(/GREEN GROCER/)).toBeInTheDocument();
  });

  it("offers the biggest four categories, the rest behind a button, and keeps a picked one in view", async () => {
    const many = { Groceries: 600, Coffee: 500, Other: 400, Bars: 300, Dining: 200, Sweets: 100 };
    get.mockImplementation((path) => (path === "months"
      ? Promise.resolve({ months: [{ ...month("2026-02", 2100), categories: { Food: many } }], data_through: {} })
      : Promise.resolve({ transactions: CHARGES })));
    render(<Block ym="2026-02" block="Food" />);
    const show = await screen.findByRole("group", { name: "Show" });
    const names = () => within(show).getAllByRole("button").map((b) => b.textContent);
    expect(names()).toEqual(["All", "Groceries", "Coffee", "Other", "Bars", "2 more"]);
    await userEvent.click(within(show).getByRole("button", { name: "2 more" }));
    expect(names()).toEqual(["All", "Groceries", "Coffee", "Other", "Bars", "Dining", "Sweets", "Fewer"]);
    await userEvent.click(within(show).getByRole("button", { name: "Sweets" }));
    await userEvent.click(within(show).getByRole("button", { name: "Fewer" }));
    expect(names()).toEqual(["All", "Groceries", "Coffee", "Other", "Bars", "Sweets", "1 more"]);
  });

  it("keeps the picked category when stepping to another month", async () => {
    answer();
    const first = render(<Block ym="2026-02" block="Food" />);
    await userEvent.click(await screen.findByRole("button", { name: "Groceries" }));
    first.unmount();
    render(<Block ym="2026-01" block="Food" />);
    expect(await screen.findByRole("img", { name: "Groceries by month" })).toBeInTheDocument();
  });

  it("a block of one category offers no choice", async () => {
    answer(CHARGES.map((c) => ({ ...c, block: "Bills", category: "Rent" })));
    render(<Block ym="2026-02" block="Bills" />);
    await screen.findByRole("heading", { name: /Bills/ });
    expect(screen.queryByRole("group", { name: "Show" })).toBeNull();
  });

  it("another block shows neither figure", async () => {
    answer(CHARGES.map((c) => ({ ...c, block: "Bills" })));
    render(<Block ym="2026-02" block="Bills" />);
    await screen.findByRole("heading", { name: /Bills/ });
    expect(screen.queryByText("Eating out")).not.toBeInTheDocument();
    expect(screen.queryByText("Eating at home")).not.toBeInTheDocument();
  });

  it("groups top merchants by merchant key, falls back to the description, sorts by total, keeps five", async () => {
    answer();
    render(<Block ym="2026-02" block="Food" />);
    const section = (await screen.findByRole("region", { name: "Top merchants" }));
    const rows = within(section).getAllByRole("listitem").map((li) => li.textContent);
    expect(rows).toHaveLength(5);
    expect(rows[0]).toMatch(/^GREEN GROCER.*\$90$/);
    expect(rows[1]).toMatch(/^CORNER CAFE.*2 charges.*\$13$/);
    expect(rows[2]).toMatch(/^CASH WITHDRAWAL.*\$12$/);
    expect(rows[3]).toMatch(/^BAKERY ONE/);
    expect(rows[4]).toMatch(/^BAKERY TWO/);
  });

  it("tapping a top merchant shows only its charges, and Show all brings the rest back", async () => {
    answer();
    const user = userEvent.setup();
    render(<Block ym="2026-02" block="Food" />);
    const top = await screen.findByRole("region", { name: "Top merchants" });
    await user.click(within(top).getByRole("button", { name: /CORNER CAFE/ }));
    const list = screen.getByRole("region", { name: "Charges" });
    expect(within(list).getByRole("heading")).toHaveTextContent("Charges at CORNER CAFE");
    expect(within(list).getAllByRole("button", { name: /CORNER CAFE/ })).toHaveLength(2);
    expect(within(list).queryByRole("button", { name: /GREEN GROCER/ })).toBeNull();
    expect(within(top).getByRole("button", { name: /CORNER CAFE/ })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(list).getByRole("button", { name: "Show all" }));
    expect(within(list).getByRole("heading")).toHaveTextContent(/^Charges$/);
    expect(within(list).getByRole("button", { name: /GREEN GROCER/ })).toBeInTheDocument();
  });

  it("tapping the chosen merchant again shows every charge", async () => {
    answer();
    const user = userEvent.setup();
    render(<Block ym="2026-02" block="Food" />);
    const top = await screen.findByRole("region", { name: "Top merchants" });
    await user.click(within(top).getByRole("button", { name: /CORNER CAFE/ }));
    await user.click(within(top).getByRole("button", { name: /CORNER CAFE/ }));
    expect(within(screen.getByRole("region", { name: "Charges" })).getByRole("button", { name: /GREEN GROCER/ }))
      .toBeInTheDocument();
  });

  it("lists every charge newest first, and tapping one goes to #/charge/<id>", async () => {
    answer();
    const user = userEvent.setup();
    render(<Block ym="2026-02" block="Food" />);
    const list = await screen.findByRole("region", { name: "Charges" });
    const buttons = within(list).getAllByRole("button");
    expect(buttons).toHaveLength(7);
    expect(buttons[0]).toHaveTextContent("BAKERY THREE");
    expect(buttons[6]).toHaveTextContent("CORNER CAFE");
    await user.click(within(list).getByRole("button", { name: /GREEN GROCER/ }));
    expect(location.hash).toBe("#/charge/2");
  });

  it("marks an unconfirmed charge", async () => {
    answer();
    render(<Block ym="2026-02" block="Food" />);
    expect(await screen.findAllByText("unconfirmed")).toHaveLength(1);
  });

  it("shows a plain error with Retry", async () => {
    get.mockRejectedValue(new Error("down"));
    const user = userEvent.setup();
    render(<Block ym="2026-02" block="Food" />);
    expect(await screen.findByText("Couldn't load this. Try again.")).toBeInTheDocument();
    answer();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Eating out")).toBeInTheDocument();
  });
});
