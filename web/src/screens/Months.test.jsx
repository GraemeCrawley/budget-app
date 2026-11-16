import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { get } from "../api.js";
import Months from "./Months.jsx";

vi.mock("../api.js", () => ({ get: vi.fn() }));

const month = (ym, extra = {}) => ({ month: ym, income_cents: 400000, spending_cents: 300000, savings_rate: 0.25,
  complete: true, uncategorised_count: 0, unconfirmed_income_count: 0, ...extra });

beforeEach(() => {
  get.mockReset();
});

describe("Months", () => {
  it("lists every month, newest first, each a link to its own page with rate, in and out", async () => {
    get.mockResolvedValue({ months: [month("2026-01"), month("2026-02", { savings_rate: null, income_cents: 0 })] });
    render(<Months />);
    const links = await screen.findAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["#/month/2026-02", "#/month/2026-01"]);
    expect(links[1]).toHaveTextContent("January 2026");
    expect(links[1]).toHaveTextContent("25%");
    expect(links[1]).toHaveTextContent("In $4,000 · Out $3,000");
    expect(links[0]).toHaveTextContent("–");
  });

  it("marks a month that is not full yet and one with charges to look at", async () => {
    get.mockResolvedValue({ months: [month("2026-01", { uncategorised_count: 2 }), month("2026-02", { complete: false })] });
    render(<Months />);
    const links = await screen.findAllByRole("link");
    expect(links[0]).toHaveTextContent("so far");
    expect(links[1]).toHaveTextContent("2 to look at");
  });

  it("says there is nothing yet when there are no months", async () => {
    get.mockResolvedValue({ months: [] });
    render(<Months />);
    expect(await screen.findByText("No months yet. Add a file to start.")).toBeInTheDocument();
  });
});
