import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChargeRow from "./ChargeRow.jsx";

const charge = (extra = {}) => ({
  id: 3, date: "2026-07-18", amount_cents: -1234, description: "FUELCO # 44172 FUELC TORONTO ON",
  account: "card", account_name: "Everyday card", kind: "spending", category: "Uncategorised",
  one_off: false, provisional: false, merchant: "FUELCO FUELC TORONTO", ...extra });

describe("ChargeRow", () => {
  it("a detailed row shows the bank's full description, the account and the date with its year", () => {
    render(<ChargeRow charge={charge()} detail onOpen={() => {}} />);
    expect(screen.getByText("FUELCO # 44172 FUELC TORONTO ON")).toBeInTheDocument();
    expect(screen.getByText("Everyday card · Jul 18, 2026")).toBeInTheDocument();
    expect(screen.queryByText(/not yet confirmed/)).not.toBeInTheDocument();
    expect(screen.queryByText(/one-off/)).not.toBeInTheDocument();
  });

  it("does not repeat the description when it is the heading", () => {
    render(<ChargeRow charge={charge({ merchant: "", description: "CASH WITHDRAWAL" })} detail onOpen={() => {}} />);
    expect(screen.getAllByText("CASH WITHDRAWAL")).toHaveLength(1);
  });

  it("says when a charge is not yet on a statement, and when it is one-off", () => {
    render(<ChargeRow charge={charge({ provisional: true, one_off: true })} detail onOpen={() => {}} />);
    expect(screen.getByText("Everyday card · Jul 18, 2026 · not yet confirmed by a statement · one-off"))
      .toBeInTheDocument();
  });

  it("stays one button that opens the charge", async () => {
    const onOpen = vi.fn();
    render(<ChargeRow charge={charge()} detail onOpen={onOpen} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("a compact row adds only the account name to its second line", () => {
    render(<ChargeRow charge={charge({ category: "Transport" })} onOpen={() => {}} />);
    expect(screen.getByText(/Transport · Everyday card/)).toBeInTheDocument();
    expect(screen.queryByText("FUELCO # 44172 FUELC TORONTO ON")).not.toBeInTheDocument();
    expect(screen.queryByText(/2026/)).not.toBeInTheDocument();
  });
});
