import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { get } from "../api.js";
import Charges from "./Charges.jsx";

vi.mock("../api.js", () => ({ get: vi.fn() }));

const tx = (id, date, cents, merchant, extra = {}) => ({ id, date, amount_cents: cents, description: `${merchant} 01`,
  merchant, account_name: "Card", kind: "spending", category: "Coffee", block: "Food", one_off: false,
  provisional: false, ...extra });
const ALL = [
  tx(1, "2026-02-03", -650, "CORNER CAFE"),
  tx(2, "2026-02-20", -9000, "GREEN GROCER", { category: "Groceries" }),
  tx(3, "2026-02-25", -300, "BAKERY ONE"),
  tx(4, "2026-02-15", 300000, "EMPLOYER", { kind: "income", category: "", block: null }),
];
const names = () => within(screen.getByRole("region", { name: "Charges" })).getAllByRole("button")
  .map((b) => b.querySelector("strong").textContent);

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue({ transactions: ALL });
  location.hash = "#/";
});

describe("All purchases in a month", () => {
  it("lists every purchase in date order from the 1st, with a count and total, and a way back", async () => {
    render(<Charges ym="2026-02" />);
    expect(await screen.findByText("3 charges, spending $100")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("transactions?month=2026-02");
    expect(names()).toEqual(["CORNER CAFE", "GREEN GROCER", "BAKERY ONE"]);
    await userEvent.click(screen.getByRole("button", { name: "Newest first" }));
    expect(names()).toEqual(["BAKERY ONE", "GREEN GROCER", "CORNER CAFE"]);
    expect(screen.getByRole("link", { name: /February 2026/ })).toHaveAttribute("href", "#/month/2026-02");
  });

  it("can show everything, and order by size", async () => {
    render(<Charges ym="2026-02" />);
    await userEvent.click(await screen.findByRole("button", { name: "Everything" }));
    await userEvent.click(screen.getByRole("button", { name: "Biggest first" }));
    expect(names()).toEqual(["EMPLOYER", "GREEN GROCER", "CORNER CAFE", "BAKERY ONE"]);
    expect(screen.getByText("4 charges, spending $100")).toBeInTheDocument();
  });

  it("narrows by shop or category as you type, and says when nothing matches", async () => {
    render(<Charges ym="2026-02" />);
    const box = await screen.findByLabelText("Narrow by shop, category or account");
    await userEvent.type(box, "grocer");
    expect(names()).toEqual(["GREEN GROCER"]);
    await userEvent.clear(box);
    await userEvent.type(box, "coffee");
    expect(names()).toEqual(["CORNER CAFE", "BAKERY ONE"]);
    await userEvent.type(box, "zzz");
    expect(screen.getByText("Nothing matches.")).toBeInTheDocument();
  });

  it("opens a charge when tapped", async () => {
    render(<Charges ym="2026-02" />);
    await userEvent.click((await screen.findAllByRole("button", { name: /BAKERY ONE/ }))[0]);
    expect(location.hash).toBe("#/charge/3");
  });
});
