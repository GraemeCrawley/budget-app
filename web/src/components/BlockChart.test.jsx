import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import BlockChart, { windowOf } from "./BlockChart.jsx";

const ym = (i) => `${2025 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`;
const months = Array.from({ length: 24 }, (_, i) => ({ month: ym(i), blocks: { Bills: (i + 1) * 10000 } }));

describe("BlockChart", () => {
  it("shows at most twelve months: the latest year when the chosen month is in it", () => {
    const shown = windowOf(months, "2026-10");
    expect(shown).toHaveLength(12);
    expect(shown.at(-1).month).toBe("2026-12");
  });

  it("an older chosen month is kept in view with three months after it", () => {
    const shown = windowOf(months, "2025-06").map((m) => m.month);
    expect(shown).toHaveLength(12);
    expect(shown).toContain("2025-06");
    expect(shown.at(-1)).toBe("2025-12");
    expect(windowOf(months, "2025-11").map((m) => m.month).at(-1)).toBe("2026-02");
  });

  it("a short history is shown whole", () => {
    expect(windowOf(months.slice(0, 5), "2025-02")).toHaveLength(5);
  });

  it("no amounts are written on the bars, and only twelve months link", () => {
    const { container } = render(<BlockChart months={months} block="Bills" chosen="2026-10" />);
    expect(container.querySelectorAll(".chartlinks a")).toHaveLength(11);
    const written = [...container.querySelectorAll("svg text")].map((t) => t.textContent).filter((t) => t.startsWith("$"));
    expect(written).toEqual([]);
  });

  it("pressing a bar's slice reads that month's amount", () => {
    const { container } = render(<BlockChart months={months} block="Bills" chosen="2026-10" />);
    container.querySelector(".plot").getBoundingClientRect = () => ({ left: 0, width: 240, top: 0, height: 140 });
    fireEvent.pointerDown(container.querySelector(".chartwrap"), { clientX: 30, pointerType: "touch" }); // second slice of 12
    expect(screen.getByRole("status").textContent).toBe("February 2026 $1,400");
  });
});
