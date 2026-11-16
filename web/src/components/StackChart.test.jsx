import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { groupsIn } from "../blockColours.js";
import StackChart from "./StackChart.jsx";

const months = [
  { month: "2026-01", blocks: { Food: 60000, Bills: 180000, Buckets: 0 } },
  { month: "2026-02", blocks: { Food: 50000, Bills: 170000, Hobbies: 4000 } },
  { month: "2026-03", blocks: { Food: 70000, Bills: 190000 } },
];

describe("StackChart", () => {
  it("lists the groups that have spending, in the fixed order with unknown ones last", () => {
    expect(groupsIn(months)).toEqual(["Bills", "Food", "Hobbies"]);
  });

  it("the key above the chart gives the chosen month's amount for each group", () => {
    render(<StackChart months={months} chosen="2026-03" />);
    const key = screen.getByRole("list", { name: "Groups in March 2026" });
    expect([...key.children].map((li) => li.textContent)).toEqual(["Bills$1,900", "Food$700", "Hobbies$0"]);
    expect(screen.getByRole("status").textContent).toBe("March 2026$2,600");
    const chart = screen.getByRole("img");
    expect(key.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy(); // key first
  });

  it("pressing another month reads its total and its groups in the key", () => {
    const { container } = render(<StackChart months={months} chosen="2026-03" />);
    container.querySelector(".plot").getBoundingClientRect = () => ({ left: 0, width: 300, top: 0, height: 160 });
    fireEvent.pointerDown(container.querySelector(".chartwrap"), { clientX: 150, pointerType: "touch" });
    expect(screen.getByRole("status").textContent).toBe("February 2026$2,240");
    const key = screen.getByRole("list", { name: "Groups in February 2026" });
    expect(within(key).getByText("$40")).toBeInTheDocument();
  });

  it("every other month is a link to that month", () => {
    const { container } = render(<StackChart months={months} chosen="2026-03" />);
    expect([...container.querySelectorAll(".chartlinks a")].map((a) => a.getAttribute("href")))
      .toEqual(["#/month/2026-01", "#/month/2026-02"]);
  });
});
