import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { get } from "../api.js";
import DailyChart from "./DailyChart.jsx";

vi.mock("../api.js", () => ({ get: vi.fn() }));

const t = (date, amount_cents, block) => ({ date, amount_cents, block });
const BY_MONTH = {
  "transactions?month=2026-02": { transactions: [t("2026-02-01", -150000, "Bills"), t("2026-02-10", -5000, "Food")] },
  "transactions?month=2026-01": { transactions: [t("2026-01-05", -100000, "Bills")] },
};

beforeEach(() => { get.mockReset(); get.mockImplementation((path) => Promise.resolve(BY_MONTH[path])); });

describe("DailyChart", () => {
  it("lists each group's spending by the month's end, and the month before by the same day", async () => {
    render(<DailyChart ym="2026-02" before="2026-01" />);
    const key = await screen.findByRole("list", { name: "Spent by Feb 28" });
    expect([...key.children].map((li) => li.textContent)).toEqual(["Bills$1,500", "Food$50", "January by then$1,000"]);
  });

  it("the last day of a longer month is set against the whole of the shorter month before", async () => {
    get.mockImplementation((path) => Promise.resolve({ transactions: path.endsWith("2026-03")
      ? [t("2026-03-31", -7000, "Food")] : [t("2026-02-27", -4000, "Food")] }));
    render(<DailyChart ym="2026-03" before="2026-02" />);
    const key = await screen.findByRole("list", { name: "Spent by Mar 31" });
    expect(key.textContent).toContain("February by then$40");
  });

  it("pressing a day reads the running total and each group so far", async () => {
    const { container } = render(<DailyChart ym="2026-02" before="2026-01" />);
    await screen.findByRole("img", { name: "Spending so far by day and group" });
    container.querySelector(".plot").getBoundingClientRect = () => ({ left: 0, width: 270, top: 0, height: 160 });
    fireEvent.pointerDown(container.querySelector(".chartwrap"), { clientX: 40, pointerType: "touch" }); // day 5
    expect(screen.getByRole("status").textContent).toBe("By Feb 5$1,500");
    expect(screen.getByRole("list", { name: "Spent by Feb 5" }).textContent).toContain("Food$0");
  });

  it("shows nothing for a month with no spending, and asks for no earlier month when there is none", async () => {
    get.mockImplementation(() => Promise.resolve({ transactions: [] }));
    const { container } = render(<DailyChart ym="2026-02" />);
    await vi.waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    expect(container.textContent).toBe("");
  });
});
