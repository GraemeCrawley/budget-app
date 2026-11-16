import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { get, send } from "../api.js";
import { reloadPage } from "../reload.js";
import Charge from "./Charge.jsx";

vi.mock("../api.js", () => ({ get: vi.fn(), send: vi.fn() }));
vi.mock("../reload.js", () => ({ reloadPage: vi.fn() }));

const failure = (status) => Object.assign(new Error("failed"), { status, detail: "failed" });

const CATEGORIES = { categories: ["Coffee", "Groceries", "Gifts"],
  blocks: { Coffee: "Food", Groceries: "Food", Gifts: "Everything else" } };

function charge(extra = {}) {
  return { id: 7, date: "2026-01-14", amount_cents: -1234, description: "GREEN GROCER 114 SAMPLETOWN",
    account: "card", account_name: "Card", kind: "spending", category: "Groceries", block: "Food",
    one_off: false, provisional: false, why: "rule: grocery stores", guessed: false,
    merchant: "CORNER CAFE", merchant_charges: 3, ...extra };
}

let current;
function show(extra) {
  current = charge(extra);
  get.mockImplementation((path) => {
    if (path === "transactions/7") return Promise.resolve(current);
    if (path === "categories") return Promise.resolve(CATEGORIES);
    return Promise.reject(new Error(`unexpected ${path}`));
  });
}

async function pick(user, category) {
  await user.click(await screen.findByRole("button", { name: "Change category" }));
  await user.click(await screen.findByRole("button", { name: new RegExp(`^${category}`) }));
}

beforeEach(() => {
  get.mockReset();
  send.mockReset();
  location.hash = "#/charge/7";
});

describe("Charge", () => {
  it("shows the exact amount, the raw description, the account and why it has its category", async () => {
    show();
    render(<Charge id="7" />);
    expect(await screen.findByText("-$12.34")).toBeInTheDocument();
    expect(screen.getByText("GREEN GROCER 114 SAMPLETOWN")).toBeInTheDocument();
    expect(screen.getByText("Card")).toBeInTheDocument();
    expect(screen.getByText("Groceries")).toBeInTheDocument();
    expect(screen.getByText("Why: rule: grocery stores")).toBeInTheDocument();
  });

  it("never offers to assign the charge to a bucket", async () => {
    show();
    render(<Charge id="7" />);
    await screen.findByText("-$12.34");
    expect(screen.queryByText(/bucket/i)).not.toBeInTheDocument();
  });

  it("asks just this or all N when the merchant has several charges, and 'All 3' posts the merchant rule", async () => {
    show();
    send.mockResolvedValue({ merchant: "CORNER CAFE", charges: 3 });
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    expect(screen.getByText("Just this charge, or all 3 from CORNER CAFE?")).toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
    current = charge({ category: "Coffee", why: "rule: you said CORNER CAFE" });
    await user.click(screen.getByRole("button", { name: "All 3" }));
    expect(send).toHaveBeenCalledWith("POST", "transactions/7/merchant-rule", { kind: "spending", category: "Coffee" });
    expect(await screen.findByText("Why: rule: you said CORNER CAFE")).toBeInTheDocument();
    expect(screen.queryByText(/Just this charge, or all/)).not.toBeInTheDocument();
  });

  it("'Just this' puts the override and shows what the server returned", async () => {
    show();
    send.mockResolvedValue(charge({ category: "Coffee", why: "you set this" }));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    await user.click(screen.getByRole("button", { name: "Just this" }));
    expect(send).toHaveBeenCalledWith("PUT", "transactions/7/override", { category: "Coffee" });
    expect(await screen.findByText("Why: you set this")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo my change" })).toBeInTheDocument();
  });

  it("with one charge the override is sent at once, no question, and a quiet line offers the merchant rule", async () => {
    show({ merchant_charges: 1 });
    send.mockResolvedValueOnce((({ merchant_charges, ...rest }) => rest)(charge({ category: "Coffee", why: "you set this" })));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    expect(send).toHaveBeenCalledWith("PUT", "transactions/7/override", { category: "Coffee" });
    expect(screen.queryByText(/Just this charge, or all/)).not.toBeInTheDocument();
    send.mockResolvedValueOnce({ merchant: "CORNER CAFE", charges: 1 });
    current = charge({ merchant_charges: 1, category: "Coffee", why: "rule: you said CORNER CAFE" });
    await user.click(await screen.findByRole("button", { name: "Use this for CORNER CAFE from now on" }));
    expect(send).toHaveBeenLastCalledWith("POST", "transactions/7/merchant-rule", { kind: "spending", category: "Coffee" });
    expect(await screen.findByText("Why: rule: you said CORNER CAFE")).toBeInTheDocument();
  });

  it("with no merchant the override is sent at once and no merchant rule is offered", async () => {
    show({ merchant: "", merchant_charges: 0 });
    send.mockResolvedValue(charge({ merchant: "", category: "Gifts", why: "you set this" }));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Gifts");
    expect(await screen.findByText("Why: you set this")).toBeInTheDocument();
    expect(screen.queryByText(/from now on/)).not.toBeInTheDocument();
  });

  it("'Not spending' sends kind transfer", async () => {
    show();
    send.mockResolvedValue(charge({ kind: "transfer", block: null, why: "you set this" }));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await user.click(await screen.findByRole("button", { name: "Not spending" }));
    expect(send).toHaveBeenCalledWith("PUT", "transactions/7/override", { kind: "transfer" });
    expect(await screen.findByText("Why: you set this")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Not spending" })).not.toBeInTheDocument();
  });

  it("unplaced spending the server marked as a guess is not called income", async () => {
    show({ category: "Uncategorised", guessed: true, why: "no rule matched" });
    render(<Charge id="7" />);
    expect(await screen.findByText("Why: no rule matched")).toBeInTheDocument();
    expect(screen.queryByText(/looks like income/)).not.toBeInTheDocument();
  });

  it("income can be marked 'Not income', and a guessed one can be confirmed", async () => {
    show({ kind: "income", category: "", block: null, amount_cents: 15000, guessed: true, merchant: "",
      merchant_charges: 0, why: "no rule matched" });
    send.mockResolvedValue(charge({ kind: "income", category: "", amount_cents: 15000, guessed: false,
      why: "you set this", merchant: "" }));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    expect(await screen.findByRole("button", { name: "Not income" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Not spending" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes, this is income" }));
    expect(send).toHaveBeenCalledWith("PUT", "transactions/7/override", { kind: "income" });
    expect(await screen.findByText("Why: you set this")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yes, this is income" })).not.toBeInTheDocument();
  });

  it("the one-off toggle sends one_off", async () => {
    show();
    send.mockResolvedValue(charge({ one_off: true, why: "you set this" }));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    const toggle = await screen.findByRole("switch", { name: "One-off" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await user.click(toggle);
    expect(send).toHaveBeenCalledWith("PUT", "transactions/7/override", { one_off: true });
    expect(await screen.findByRole("switch", { name: "One-off" })).toHaveAttribute("aria-checked", "true");
  });

  it("'Undo my change' appears only when the charge says 'you set this', and deletes the override", async () => {
    show();
    const { unmount } = render(<Charge id="7" />);
    await screen.findByText("-$12.34");
    expect(screen.queryByRole("button", { name: "Undo my change" })).not.toBeInTheDocument();
    unmount();

    show({ why: "you set this", category: "Coffee" });
    send.mockResolvedValue(charge());
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await user.click(await screen.findByRole("button", { name: "Undo my change" }));
    expect(send).toHaveBeenCalledWith("DELETE", "transactions/7/override");
    expect(await screen.findByText("Why: rule: grocery stores")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo my change" })).not.toBeInTheDocument();
  });

  it("a failed save says so and leaves the shown category and why unchanged", async () => {
    show({ merchant_charges: 1 });
    send.mockRejectedValue(new Error("down"));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    expect(await screen.findByText("Couldn't save that. Try again.")).toBeInTheDocument();
    expect(screen.getByText("Groceries")).toBeInTheDocument();
    expect(screen.getByText("Why: rule: grocery stores")).toBeInTheDocument();
  });

  for (const [status, words, offer] of [[0, "Couldn't reach the app. Your sign-in may have expired.", "Reload"],
    [401, "Your sign-in has expired.", "Sign in again"]]) {
    it(`a load that fails with status ${status} offers a reload or a sign-in instead of Retry`, async () => {
      reloadPage.mockReset();
      show();
      get.mockRejectedValueOnce(failure(status));
      const user = userEvent.setup();
      render(<Charge id="7" />);
      expect(await screen.findByText(words)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: offer }));
      expect(reloadPage).toHaveBeenCalledOnce();
    });

    it(`a save that fails with status ${status} offers a reload or a sign-in instead of Try again`, async () => {
      show({ merchant_charges: 1 });
      send.mockRejectedValue(failure(status));
      const user = userEvent.setup();
      render(<Charge id="7" />);
      await pick(user, "Coffee");
      expect(await screen.findByText(words)).toBeInTheDocument();
      expect(screen.queryByText("Couldn't save that. Try again.")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: offer })).toBeInTheDocument();
    });
  }

  it("a save that fails with status 500 still offers Try again", async () => {
    show({ merchant_charges: 1 });
    send.mockRejectedValue(failure(500));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    expect(await screen.findByText("Couldn't save that. Try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByText("Your sign-in has expired.")).not.toBeInTheDocument();
  });

  it("a failed load shows a plain error with Retry", async () => {
    show();
    get.mockRejectedValueOnce(new Error("down"));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    expect(await screen.findByText("Couldn't load this. Try again.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("-$12.34")).toBeInTheDocument();
  });

  it("a failed merchant-rule POST offers Try again, which resends the same request", async () => {
    show();
    send.mockRejectedValueOnce(new Error("down"));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    await user.click(screen.getByRole("button", { name: "All 3" }));
    expect(await screen.findByText("Couldn't save that. Try again.")).toBeInTheDocument();
    expect(screen.getByText("Groceries")).toBeInTheDocument();
    send.mockResolvedValueOnce({ merchant: "CORNER CAFE", charges: 3 });
    current = charge({ category: "Coffee", why: "rule: you said CORNER CAFE" });
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[1]).toEqual(send.mock.calls[0]);
    expect(await screen.findByText("Why: rule: you said CORNER CAFE")).toBeInTheDocument();
    expect(screen.queryByText("Couldn't save that. Try again.")).not.toBeInTheDocument();
  });

  it("a failed 'Just this' keeps the question and Try again resends the same override", async () => {
    show();
    send.mockRejectedValueOnce(new Error("down"));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    await user.click(screen.getByRole("button", { name: "Just this" }));
    expect(await screen.findByText("Couldn't save that. Try again.")).toBeInTheDocument();
    expect(screen.getByText("Just this charge, or all 3 from CORNER CAFE?")).toBeInTheDocument();
    send.mockResolvedValueOnce(charge({ category: "Coffee", why: "you set this" }));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(send).toHaveBeenLastCalledWith("PUT", "transactions/7/override", { category: "Coffee" });
    expect(send.mock.calls[1]).toEqual(send.mock.calls[0]);
    expect(await screen.findByText("Why: you set this")).toBeInTheDocument();
    expect(screen.queryByText(/Just this charge, or all/)).not.toBeInTheDocument();
  });

  it("a failed direct save after the sheet closed can be retried without picking again", async () => {
    show({ merchant_charges: 1 });
    send.mockRejectedValueOnce(new Error("down"));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    expect(await screen.findByText("Couldn't save that. Try again.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    send.mockResolvedValueOnce(charge({ merchant_charges: undefined, category: "Coffee", why: "you set this" }));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(send).toHaveBeenLastCalledWith("PUT", "transactions/7/override", { category: "Coffee" });
    expect(await screen.findByText("Why: you set this")).toBeInTheDocument();
  });

  it("when the save worked but the reload failed, says so with Retry instead of showing the old charge", async () => {
    show();
    send.mockResolvedValue({ merchant: "CORNER CAFE", charges: 3 });
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    get.mockRejectedValueOnce(new Error("down"));
    await user.click(screen.getByRole("button", { name: "All 3" }));
    expect(await screen.findByText("Saved, but couldn't reload this charge. Try again.")).toBeInTheDocument();
    expect(screen.queryByText("Groceries")).not.toBeInTheDocument();
    current = charge({ category: "Coffee", why: "rule: you said CORNER CAFE" });
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Why: rule: you said CORNER CAFE")).toBeInTheDocument();
  });

  it("Cancel drops the question and any save error, and sends nothing", async () => {
    show();
    send.mockRejectedValueOnce(new Error("down"));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    await user.click(screen.getByRole("button", { name: "Just this" }));
    await screen.findByText("Couldn't save that. Try again.");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/Just this charge, or all/)).not.toBeInTheDocument();
    expect(screen.queryByText("Couldn't save that. Try again.")).not.toBeInTheDocument();
    expect(send).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Groceries")).toBeInTheDocument();
  });

  it("the merchant offer goes away when the charge is then marked not spending, and no rule can be posted", async () => {
    show({ merchant_charges: 1 });
    send.mockResolvedValueOnce(charge({ category: "Coffee", why: "you set this" }));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    expect(await screen.findByRole("button", { name: "Use this for CORNER CAFE from now on" })).toBeInTheDocument();
    send.mockResolvedValueOnce(charge({ category: "Coffee", kind: "transfer", block: null, why: "you set this" }));
    await user.click(screen.getByRole("button", { name: "Not spending" }));
    expect(await screen.findByText("Not counted")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /from now on/ })).not.toBeInTheDocument();
  });

  it("the offer also goes away after a one-off change", async () => {
    show({ merchant_charges: 1 });
    send.mockResolvedValueOnce(charge({ category: "Coffee", why: "you set this" }));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await pick(user, "Coffee");
    await screen.findByRole("button", { name: "Use this for CORNER CAFE from now on" });
    send.mockResolvedValueOnce(charge({ category: "Coffee", one_off: true, why: "you set this" }));
    await user.click(screen.getByRole("switch", { name: "One-off" }));
    await screen.findByRole("switch", { name: "One-off", checked: true });
    expect(screen.queryByRole("button", { name: /from now on/ })).not.toBeInTheDocument();
  });

  it("does not offer Change category for a charge counted as income", async () => {
    show({ kind: "income", category: "", block: null, amount_cents: 15000, merchant: "", merchant_charges: 0 });
    render(<Charge id="7" />);
    await screen.findByText("$150.00");
    expect(screen.queryByRole("button", { name: "Change category" })).not.toBeInTheDocument();
  });

  it("shows the date with its year, and does not repeat the bank description when there is no merchant", async () => {
    show({ merchant: "", merchant_charges: 0 });
    render(<Charge id="7" />);
    expect(await screen.findByText("Jan 14, 2026")).toBeInTheDocument();
    expect(screen.getAllByText("GREEN GROCER 114 SAMPLETOWN")).toHaveLength(1);
  });

  it("'Can't remember' files just this charge, with no question about the shop's other charges and no rule offered", async () => {
    show({ category: "Uncategorised", block: "Everything else", why: "no rule matched" });
    send.mockResolvedValue(charge({ category: "Can't remember", block: "Everything else", why: "you set this" }));
    const user = userEvent.setup();
    render(<Charge id="7" />);
    await user.click(await screen.findByRole("button", { name: "Can't remember" }));
    expect(send.mock.calls).toEqual([["PUT", "transactions/7/override", { category: "Can't remember" }]]);
    expect(await screen.findByText("you set this", { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Can't remember" })).toBeNull(); // already filed there
    expect(screen.queryByRole("button", { name: /from now on/ })).toBeNull();
  });

  it("income has no 'Can't remember' button", async () => {
    show({ kind: "income", category: "" });
    render(<Charge id="7" />);
    await screen.findByText("Income");
    expect(screen.queryByRole("button", { name: "Can't remember" })).toBeNull();
  });
});
