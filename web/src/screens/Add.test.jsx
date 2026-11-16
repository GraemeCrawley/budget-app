import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { get, send, upload } from "../api.js";
import Add from "./Add.jsx";

vi.mock("../api.js", () => ({ get: vi.fn(), send: vi.fn(), upload: vi.fn() }));
vi.mock("../reload.js", () => ({ reloadPage: vi.fn() }));

const ACCOUNTS = { accounts: [
  { key: "chequing", name: "Everyday", kind: "chequing", institution: "Sample Bank", export_note: "",
    data_through: "2026-01-31", ranges: [["2025-11-01", "2026-01-31"]], flip_sign: false },
  { key: "card", name: "Card", kind: "card", institution: "Other Bank", export_note: "Download from Activity, CSV",
    data_through: null, ranges: [], flip_sign: false },
] };

function batch(extra = {}) {
  return { id: 5, account: "card", account_name: "Card", kind: "activity", period_start: "2026-01-03",
    period_end: "2026-01-29", status: "accepted", added: 12, already_held: 4, confirmed: 0, differences: [],
    message: null, can_widen: false, ...extra };
}

function refusal(body, status = 422) {
  return Object.assign(new Error(body.reason), { status, detail: body.reason, body: { ok: false, ...body } });
}

const named = (name) => new File(["x"], name);
const FILE = () => new File(["x"], "export.csv", { type: "text/csv" });

beforeEach(() => {
  get.mockReset();
  send.mockReset();
  upload.mockReset();
  get.mockImplementation((path) => (path === "accounts" ? Promise.resolve(ACCOUNTS) : Promise.reject(new Error(path))));
  location.hash = "#/add";
  Element.prototype.scrollIntoView = vi.fn();
});

describe("Add", () => {
  it("lists each account with 'data through Jan 31' or 'nothing yet'", async () => {
    render(<Add />);
    expect(await screen.findByText("Data through Jan 31")).toBeInTheDocument();
    expect(screen.getByText("Nothing yet")).toBeInTheDocument();
    expect(screen.getByText("Download from Activity, CSV")).toBeInTheDocument();
    expect(screen.getByText("Add a note on how you export this one")).toBeInTheDocument();
  });

  it("choosing a file on an account card sends it with that account_key", async () => {
    upload.mockResolvedValue({ ok: true, batches: [batch()] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    const [path, form] = upload.mock.calls[0];
    expect(path).toBe("uploads");
    expect(form.get("account_key")).toBe("card");
    expect(form.get("file").name).toBe("export.csv");
    expect(form.has("signs")).toBe(false);
  });

  it("the file for any account is sent without an account_key", async () => {
    upload.mockResolvedValue({ ok: true, batches: [batch()] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for any account"), FILE());
    expect(upload.mock.calls[0][1].has("account_key")).toBe(false);
  });

  it("a statement says how many charges are on it, and still says what it confirmed", async () => {
    upload.mockResolvedValue({ ok: true, batches: [batch({ kind: "statement", period_start: "2026-01-01",
      period_end: "2026-01-31", added: 14, already_held: 0, confirmed: 11 })] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("14 charges on this statement for Card, Jan 1 to Jan 31")).toBeInTheDocument();
    expect(screen.getByText("Confirmed 11 earlier charges")).toBeInTheDocument();
    expect(screen.queryByText(/^Added/)).not.toBeInTheDocument();
  });

  it("says what was added and what was already here, then offers to review the latest month", async () => {
    upload.mockResolvedValue({ ok: true, batches: [batch(), batch({ id: 6, period_end: "2026-02-10", added: 1, already_held: 0,
      confirmed: 3, differences: ["only in the statement: 2026-02-09"], message: "this account already has a different statement for this period" })] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("Added 12 charges for Card, Jan 3 to Jan 29")).toBeInTheDocument();
    expect(screen.getByText("4 were already here")).toBeInTheDocument();
    expect(screen.getByText("Added 1 charge for Card, Jan 3 to Feb 10")).toBeInTheDocument();
    expect(screen.getByText("Confirmed 3 earlier charges")).toBeInTheDocument();
    expect(screen.getByText("this account already has a different statement for this period")).toBeInTheDocument();
    await user.click(screen.getByText("1 difference"));
    expect(screen.getByText("only in the statement: 2026-02-09")).toBeVisible();
    expect(screen.getByRole("link", { name: "Review February" })).toHaveAttribute("href", "#/review/2026-02");
  });

  it("says a duplicate was already uploaded", async () => {
    upload.mockResolvedValue({ ok: true, batches: [batch({ status: "duplicate", added: 0, already_held: 0 })] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("This file was already uploaded")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Review/ })).not.toBeInTheDocument();
  });

  it("can_widen: 'Yes, the whole month' sends the month's first and last day", async () => {
    upload.mockResolvedValue({ ok: true, batches: [batch({ can_widen: true })] });
    send.mockResolvedValue(batch({ period_start: "2026-01-01", period_end: "2026-01-31", can_widen: false }));
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("This export covers Jan 3 to Jan 29. Does it cover all of January?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes, the whole month" }));
    expect(send).toHaveBeenCalledWith("PATCH", "batches/5/period", { period_start: "2026-01-01", period_end: "2026-01-31" });
    expect(await screen.findByText("Added 12 charges for Card, Jan 1 to Jan 31")).toBeInTheDocument();
    expect(screen.queryByText(/Does it cover all of/)).not.toBeInTheDocument();
  });

  it("shows the server's reason when widening is refused", async () => {
    upload.mockResolvedValue({ ok: true, batches: [batch({ can_widen: true })] });
    send.mockRejectedValue(Object.assign(new Error("x"), { status: 422, detail: "the period cannot reach past the day it was received" }));
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    await user.click(await screen.findByRole("button", { name: "Yes, the whole month" }));
    expect(await screen.findByText("the period cannot reach past the day it was received")).toBeInTheDocument();
    expect(screen.getByText("This export covers Jan 3 to Jan 29. Does it cover all of January?")).toBeInTheDocument();
  });

  it("a signs question is answered 'Yes, they're charges' and the same File is resent with signs flip", async () => {
    upload.mockRejectedValueOnce(refusal({ code: "signs_look_reversed", reason: "Most rows look like money in.", needs: { choose_signs: true } }));
    upload.mockResolvedValueOnce({ ok: true, batches: [batch()] });
    const file = FILE();
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), file);
    expect(await screen.findByText("Are these charges shown as positive numbers?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes, they're charges" }));
    const form = upload.mock.calls[1][1];
    expect(form.get("signs")).toBe("flip");
    expect(form.get("account_key")).toBe("card");
    expect(form.get("file").name).toBe(file.name);
    expect(await screen.findByText("Added 12 charges for Card, Jan 3 to Jan 29")).toBeInTheDocument();
    expect(screen.queryByText("Are these charges shown as positive numbers?")).not.toBeInTheDocument();
  });

  it("'No, leave them' resends with signs as_is", async () => {
    upload.mockRejectedValueOnce(refusal({ code: "signs_look_reversed", reason: "r", needs: { choose_signs: true } }));
    upload.mockResolvedValueOnce({ ok: true, batches: [batch()] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    await user.click(await screen.findByRole("button", { name: "No, leave them" }));
    expect(upload.mock.calls[1][1].get("signs")).toBe("as_is");
  });

  it("a choose_account refusal lets an existing account be picked, and resends with that account_key", async () => {
    upload.mockRejectedValueOnce(refusal({ code: "account_needed", reason: "This file doesn't say which account it is for.", needs: { choose_account: true } }));
    upload.mockResolvedValueOnce({ ok: true, batches: [batch()] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for any account"), FILE());
    expect(await screen.findByText("This file doesn't say which account it is for.")).toBeInTheDocument();
    const choose = screen.getByRole("group", { name: "Which account is it for?" });
    await user.click(within(choose).getByRole("button", { name: "Card" }));
    const form = upload.mock.calls[1][1];
    expect(form.get("account_key")).toBe("card");
    expect(form.get("file").name).toBe("export.csv");
  });

  it("a choose_account refusal can make a new account and resend with its key", async () => {
    upload.mockRejectedValueOnce(refusal({ code: "account_needed", reason: "Which one?", needs: { choose_account: true } }));
    upload.mockResolvedValueOnce({ ok: true, batches: [batch({ account: "rainy-day", account_name: "Rainy day" })] });
    send.mockResolvedValue({ key: "rainy-day", name: "Rainy day", kind: "savings", institution: "", export_note: "", data_through: null, ranges: [] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for any account"), FILE());
    const choose = await screen.findByRole("group", { name: "Which account is it for?" });
    await user.click(within(choose).getByRole("button", { name: "New account" }));
    await user.type(within(choose).getByLabelText("Name"), "Rainy day");
    await user.selectOptions(within(choose).getByLabelText("Kind"), "savings");
    await user.click(within(choose).getByRole("button", { name: "Create account" }));
    expect(send).toHaveBeenCalledWith("POST", "accounts", { name: "Rainy day", kind: "savings" });
    await screen.findByText("Added 12 charges for Rainy day, Jan 3 to Jan 29");
    expect(upload.mock.calls[1][1].get("account_key")).toBe("rainy-day");
  });

  it("a new account is created from the top of the page and appears as a card", async () => {
    send.mockResolvedValue({ key: "rainy-day", name: "Rainy day", kind: "savings", institution: "", export_note: "", data_through: null, ranges: [] });
    const user = userEvent.setup();
    render(<Add />);
    await user.click(await screen.findByRole("button", { name: "New account" }));
    await user.type(screen.getByLabelText("Name"), "Rainy day");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByLabelText("Add files for Rainy day")).toBeInTheDocument();
  });

  it("a file for another account says so", async () => {
    upload.mockRejectedValue(refusal({ code: "wrong_account", reason: "This file belongs to a different account.", needs: { file_is_for: "Everyday" } }));
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("This looks like a file for Everyday.")).toBeInTheDocument();
  });

  it("an upload refused because the sign-in expired (401) asks to sign in again, not as a file refusal", async () => {
    // the server's 401 body carries a reason code too: it must not be read as a refusal of the file
    upload.mockRejectedValue(Object.assign(new Error("not signed in"),
      { status: 401, detail: "not signed in", body: { detail: "not signed in", reason: "expired" } }));
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("Your sign-in has expired.")).toBeInTheDocument();
    expect(screen.queryByText("expired")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in again" })).toBeInTheDocument();
  });

  it("an upload that never reaches the server (status 0) says so and offers a reload", async () => {
    upload.mockRejectedValue(Object.assign(new Error("could not reach the server"),
      { status: 0, detail: "could not reach the server", body: null }));
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("Couldn't reach the app. Your sign-in may have expired.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("a refusal shows its reason text exactly as given", async () => {
    upload.mockRejectedValue(refusal({ code: "failed_checks", reason: "This file didn't pass the checks: its rows or totals don't add up.", needs: null }));
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("This file didn't pass the checks: its rows or totals don't add up.")).toBeInTheDocument();
  });

  it("a file over the limit (413) shows its reason", async () => {
    upload.mockRejectedValue(refusal({ code: "too_large", reason: "This file is over 10 MB." }, 413));
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("This file is over 10 MB.")).toBeInTheDocument();
  });

  it("a failed upload says so and Try again resends the same file", async () => {
    upload.mockRejectedValueOnce(Object.assign(new Error("net"), { status: 502 }));
    upload.mockResolvedValueOnce({ ok: true, batches: [batch()] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("Couldn't add that file. Try again.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(upload.mock.calls[1][1].get("account_key")).toBe("card");
    expect(await screen.findByText("Added 12 charges for Card, Jan 3 to Jan 29")).toBeInTheDocument();
  });

  it("several files chosen at once are sent one at a time, each named with its result, with one Review link", async () => {
    upload.mockResolvedValueOnce({ ok: true, batches: [batch({ id: 1, period_end: "2026-02-10" })] });
    upload.mockResolvedValueOnce({ ok: true, batches: [batch({ id: 2, status: "duplicate" })] });
    upload.mockResolvedValueOnce({ ok: true, batches: [batch({ id: 3, added: 7 })] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), [named("a.pdf"), named("b.pdf"), named("c.pdf")]);
    expect(await screen.findByText("3 of 3 files added")).toBeInTheDocument();
    expect(upload.mock.calls.map(([, form]) => [form.get("file").name, form.get("account_key")]))
      .toEqual([["a.pdf", "card"], ["b.pdf", "card"], ["c.pdf", "card"]]);
    expect(within(screen.getByRole("group", { name: "b.pdf" })).getByText("This file was already uploaded")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "c.pdf" })).getByText("Added 7 charges for Card, Jan 3 to Jan 29")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /^Review/ });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "#/review/2026-02");
  });

  it("the next file waits for the one before it", async () => {
    let release;
    upload.mockReturnValueOnce(new Promise((r) => { release = r; }));
    upload.mockResolvedValueOnce({ ok: true, batches: [batch({ id: 2 })] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), [named("a.pdf"), named("b.pdf")]);
    expect(await screen.findByText("Adding file 1 of 2")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "b.pdf" })).getByText("Waiting")).toBeInTheDocument();
    expect(upload).toHaveBeenCalledTimes(1);
    release({ ok: true, batches: [batch({ id: 1 })] });
    expect(await screen.findByText("2 of 2 files added")).toBeInTheDocument();
  });

  it("a refused file does not hold up the rest, and its answer resends only that file", async () => {
    upload.mockRejectedValueOnce(refusal({ code: "signs_look_reversed", reason: "Signs?", needs: { choose_signs: true } }));
    upload.mockResolvedValueOnce({ ok: true, batches: [batch({ id: 2 })] });
    upload.mockResolvedValueOnce({ ok: true, batches: [batch({ id: 1 })] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), [named("a.csv"), named("b.csv")]);
    expect(await screen.findByText("1 of 2 files added")).toBeInTheDocument();
    await user.click(within(screen.getByRole("group", { name: "a.csv" })).getByRole("button", { name: "Yes, they're charges" }));
    expect(await screen.findByText("2 of 2 files added")).toBeInTheDocument();
    expect(upload).toHaveBeenCalledTimes(3);
    const form = upload.mock.calls[2][1];
    expect([form.get("file").name, form.get("signs"), form.get("account_key")]).toEqual(["a.csv", "flip", "card"]);
  });

  it("a file that could not be sent stops the run, and Try again sends it and then the rest", async () => {
    upload.mockRejectedValueOnce(Object.assign(new Error("net"), { status: 502 }));
    upload.mockResolvedValue({ ok: true, batches: [batch()] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), [named("a.pdf"), named("b.pdf")]);
    expect(await screen.findByText("Couldn't add that file. Try again.")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "b.pdf" })).getByText("Not sent yet")).toBeInTheDocument();
    expect(upload).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("2 of 2 files added")).toBeInTheDocument();
    expect(upload.mock.calls.map(([, form]) => form.get("file").name)).toEqual(["a.pdf", "a.pdf", "b.pdf"]);
  });

  it("says which finished months each account is still missing", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 3, 13) });
    try {
      render(<Add />);
      const panel = await screen.findByRole("region", { name: "Still missing" });
      const rows = within(panel).getAllByRole("listitem").map((li) => li.textContent);
      expect(rows).toEqual(["February 2026Everyday", "March 2026Everyday"]);
      expect(screen.getByRole("group", { name: "Missing for Everyday" })).toHaveTextContent("MissingFebruary, March");
      expect(screen.queryByRole("group", { name: "Missing for Card" })).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("accounts at one institution share a card: one list, one note saved on each, one upload with no account", async () => {
    const group = [
      { key: "ws-bills", name: "Bills", kind: "chequing", institution: "Wealthy", export_note: "", data_through: "2026-01-31", ranges: [] },
      { key: "ws-trip", name: "Trip", kind: "savings", institution: "Wealthy", export_note: "Tap CSV", data_through: null, ranges: [] },
    ];
    get.mockImplementation(() => Promise.resolve({ accounts: [...group, ACCOUNTS.accounts[1]] }));
    send.mockImplementation((_m, path, body) => Promise.resolve({ ...group.find((a) => path.endsWith(a.key)), ...body }));
    upload.mockResolvedValue({ ok: true, batches: [batch()] });
    const user = userEvent.setup();
    render(<Add />);
    const card = await screen.findByRole("region", { name: "Wealthy" });
    expect(within(card).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["BillsData through Jan 31", "TripNothing yet"]);
    expect(screen.getByRole("region", { name: "Card" })).toBeInTheDocument();
    expect(within(card).getByText("Tap CSV")).not.toBeVisible(); // folded away until opened
    await user.click(within(card).getByText("How to export"));
    expect(within(card).getByText("Tap CSV")).toBeVisible();
    await user.click(within(card).getByRole("button", { name: "Edit note" }));
    await user.type(within(card).getByLabelText("How you export these"), ", then save");
    await user.click(within(card).getByRole("button", { name: "Save note" }));
    expect(send.mock.calls.map(([, path, body]) => [path, body.export_note])).toEqual([
      ["accounts/ws-bills", "Tap CSV, then save"], ["accounts/ws-trip", "Tap CSV, then save"]]);
    expect(await within(card).findByText("Tap CSV, then save")).toBeInTheDocument();
    await user.upload(within(card).getByLabelText("Add files for Wealthy"), FILE());
    expect(upload.mock.calls[0][1].has("account_key")).toBe(false);
  });

  it("an account that lacks only some days of a month says which days", async () => {
    get.mockImplementation(() => Promise.resolve({ accounts: [
      { ...ACCOUNTS.accounts[1], data_through: "2026-03-31", ranges: [["2026-01-01", "2026-01-28"], ["2026-01-31", "2026-03-31"]] }] }));
    vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 3, 13) });
    try {
      render(<Add />);
      const panel = await screen.findByRole("region", { name: "Still missing" });
      expect(within(panel).getByRole("listitem").textContent).toBe("January 2026Card");
      expect(screen.getByRole("group", { name: "Missing for Card" })).toHaveTextContent("MissingJan 29 to Jan 30");
    } finally {
      vi.useRealTimers();
    }
  });

  it("an institution is named once per month, and its card says what each of its accounts lacks", async () => {
    const group = [
      { key: "ws-bills", name: "Bills", kind: "chequing", institution: "Wealthy", export_note: "", data_through: "2026-01-31", ranges: [["2026-01-01", "2026-01-31"]] },
      { key: "ws-trip", name: "Trip", kind: "savings", institution: "Wealthy", export_note: "", data_through: "2026-02-28", ranges: [["2026-01-01", "2026-02-28"]] },
    ];
    get.mockImplementation(() => Promise.resolve({ accounts: group }));
    vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 3, 13) });
    try {
      render(<Add />);
      const panel = await screen.findByRole("region", { name: "Still missing" });
      expect(within(panel).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["February 2026Wealthy", "March 2026Wealthy"]);
      const lacks = screen.getByRole("group", { name: "Missing for Wealthy" });
      expect(within(lacks).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Bills: February, March", "Trip: March"]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("an account whose next statement is not out yet is not missing, and its card says so", async () => {
    get.mockImplementation(() => Promise.resolve({ accounts: [
      { ...ACCOUNTS.accounts[1], data_through: "2026-03-14", ranges: [["2026-02-15", "2026-03-14"]] }] }));
    vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 3, 13) });
    try {
      render(<Add />);
      const panel = await screen.findByRole("region", { name: "Still missing" });
      expect(within(panel).queryByRole("listitem")).toBeNull();
      expect(screen.queryByRole("group", { name: "Missing for Card" })).toBeNull();
      expect(screen.getByText("Nothing to fetch yet. Charges after Mar 14 come with the next statement.")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("the export note is edited in place and saved with PATCH", async () => {
    send.mockResolvedValue({ ...ACCOUNTS.accounts[0], export_note: "Menu, Export, CSV" });
    const user = userEvent.setup();
    render(<Add />);
    await user.click(await screen.findByText("Add a note on how you export this one"));
    await user.type(screen.getByLabelText("How you export this one"), "Menu, Export, CSV");
    await user.click(screen.getByRole("button", { name: "Save note" }));
    expect(send).toHaveBeenCalledWith("PATCH", "accounts/chequing", { export_note: "Menu, Export, CSV" });
    expect(await screen.findByText("Menu, Export, CSV")).toBeInTheDocument();
  });

  it("a failed note save keeps what was typed and Try again resends it", async () => {
    send.mockRejectedValueOnce(Object.assign(new Error("net"), { status: 502 }));
    send.mockResolvedValueOnce({ ...ACCOUNTS.accounts[0], export_note: "Menu" });
    const user = userEvent.setup();
    render(<Add />);
    await user.click(await screen.findByText("Add a note on how you export this one"));
    await user.type(screen.getByLabelText("How you export this one"), "Menu");
    await user.click(screen.getByRole("button", { name: "Save note" }));
    expect(await screen.findByText("Couldn't save that. Try again.")).toBeInTheDocument();
    expect(screen.getByLabelText("How you export this one")).toHaveValue("Menu");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(send).toHaveBeenLastCalledWith("PATCH", "accounts/chequing", { export_note: "Menu" });
    expect(await screen.findByText("Menu")).toBeInTheDocument();
  });

  it("a failed load says so with a retry", async () => {
    get.mockRejectedValueOnce(Object.assign(new Error("net"), { status: 502 }));
    const user = userEvent.setup();
    render(<Add />);
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Data through Jan 31")).toBeInTheDocument();
  });
  it("brings the outcome into view: it is scrolled to, focused and a polite live region", async () => {
    upload.mockResolvedValue({ ok: true, batches: [batch()] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    await screen.findByText("Added 12 charges for Card, Jan 3 to Jan 29");
    const outcome = screen.getByTestId("outcome");
    expect(outcome).toHaveAttribute("aria-live", "polite");
    expect(outcome).toHaveAttribute("tabindex", "-1");
    expect(document.activeElement).toBe(outcome);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    expect(outcome).toContainElement(screen.getByRole("link", { name: "Review January" }));
  });

  it("brings a refusal and a failure into view too", async () => {
    upload.mockRejectedValueOnce(refusal({ code: "failed_checks", reason: "No good.", needs: null }));
    upload.mockRejectedValueOnce(Object.assign(new Error("net"), { status: 502 }));
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    await screen.findByText("No good.");
    expect(document.activeElement).toBe(screen.getByTestId("outcome"));
    await user.upload(screen.getByLabelText("Add files for Card"), FILE());
    const failed = await screen.findByText("Couldn't add that file. Try again.");
    expect(screen.getByTestId("outcome")).toContainElement(failed);
    expect(document.activeElement).toBe(screen.getByTestId("outcome"));
  });

  it("a Try again after a success has nothing to resend: the file is not kept", async () => {
    upload.mockRejectedValueOnce(Object.assign(new Error("net"), { status: 502 }));
    upload.mockResolvedValueOnce({ ok: true, batches: [batch()] });
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    await screen.findByText("Added 12 charges for Card, Jan 3 to Jan 29");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(upload).toHaveBeenCalledTimes(2);
  });

  it("choosing the same file twice in a row sends it twice", async () => {
    upload.mockResolvedValue({ ok: true, batches: [batch()] });
    const user = userEvent.setup();
    render(<Add />);
    const input = await screen.findByLabelText("Add files for Card");
    const file = FILE();
    await user.upload(input, file);
    await screen.findByText("Added 12 charges for Card, Jan 3 to Jan 29");
    await user.upload(screen.getByLabelText("Add files for Card"), file);
    await vi.waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
  });

  it("a double tap on an answer sends one upload", async () => {
    let release;
    upload.mockRejectedValueOnce(refusal({ code: "signs_look_reversed", reason: "r", needs: { choose_signs: true } }));
    upload.mockReturnValueOnce(new Promise((r) => { release = r; }));
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    await user.dblClick(await screen.findByRole("button", { name: "Yes, they're charges" }));
    expect(upload).toHaveBeenCalledTimes(2);
    release({ ok: true, batches: [batch()] });
    await screen.findByText("Added 12 charges for Card, Jan 3 to Jan 29");
  });

  it("a file that needs an account and then asks about signs is sent with both answers", async () => {
    upload.mockRejectedValueOnce(refusal({ code: "account_needed", reason: "Which?", needs: { choose_account: true } }));
    upload.mockRejectedValueOnce(refusal({ code: "signs_look_reversed", reason: "Signs?", needs: { choose_signs: true } }));
    upload.mockResolvedValueOnce({ ok: true, batches: [batch()] });
    const file = FILE();
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for any account"), file);
    const choose = await screen.findByRole("group", { name: "Which account is it for?" });
    await user.click(within(choose).getByRole("button", { name: "Card" }));
    await user.click(await screen.findByRole("button", { name: "Yes, they're charges" }));
    const form = upload.mock.calls[2][1];
    expect(form.get("account_key")).toBe("card");
    expect(form.get("signs")).toBe("flip");
    expect(form.get("file").name).toBe(file.name);
  });

  it("an export across two months asks about both, and widens from the first of one to the last of the other", async () => {
    upload.mockResolvedValue({ ok: true, batches: [batch({ can_widen: true, period_start: "2026-01-20", period_end: "2026-02-10" })] });
    send.mockResolvedValue(batch({ period_start: "2026-01-01", period_end: "2026-02-28" }));
    const user = userEvent.setup();
    render(<Add />);
    await user.upload(await screen.findByLabelText("Add files for Card"), FILE());
    expect(await screen.findByText("This export covers Jan 20 to Feb 10. Does it cover January to February in full?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes, the whole month" }));
    expect(send).toHaveBeenCalledWith("PATCH", "batches/5/period", { period_start: "2026-01-01", period_end: "2026-02-28" });
  });

  it("an export_note that arrives as null is treated as empty", async () => {
    get.mockImplementation(() => Promise.resolve({ accounts: [{ ...ACCOUNTS.accounts[0], export_note: null }] }));
    const user = userEvent.setup();
    render(<Add />);
    await user.click(await screen.findByText("Add a note on how you export this one"));
    expect(screen.getByLabelText("How you export this one")).toHaveValue("");
  });

  it("a shown 409 message from a new account goes away when the name is edited", async () => {
    send.mockRejectedValue(Object.assign(new Error("x"), { status: 409, detail: "an account with that name already exists" }));
    const user = userEvent.setup();
    render(<Add />);
    await user.click(await screen.findByRole("button", { name: "New account" }));
    await user.type(screen.getByLabelText("Name"), "Card");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("an account with that name already exists")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Name"), "s");
    expect(screen.queryByText("an account with that name already exists")).not.toBeInTheDocument();
  });
});
