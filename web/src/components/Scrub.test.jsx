import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import MoneyChart from "./MoneyChart.jsx";
import RateChart from "./RateChart.jsx";

const months = [
  { month: "2026-01", savings_rate: 0.2, income_cents: 500000, spending_cents: 400000 },
  { month: "2026-02", savings_rate: null, income_cents: 0, spending_cents: 120000 },
  { month: "2026-03", savings_rate: -1.5, income_cents: 200000, spending_cents: 500000 },
];

// The plot area is 200 wide starting at x=100, so the three months sit at 100, 200 and 300.
function plotOf(container) {
  const plot = container.querySelector(".plot");
  plot.getBoundingClientRect = () => ({ left: 100, width: 200, top: 0, height: 160 });
  return container.querySelector(".chartwrap");
}

describe("reading a chart by pressing and dragging", () => {
  it("shows nothing until the chart is pressed", () => {
    render(<RateChart months={months} links={false} />);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("a press shows that month's rate, and dragging moves to the next months", () => {
    const { container } = render(<RateChart months={months} links={false} />);
    const wrap = plotOf(container);
    fireEvent.pointerDown(wrap, { clientX: 105, pointerType: "touch" });
    expect(screen.getByRole("status").textContent).toBe("January 2026 20%");
    fireEvent.pointerMove(wrap, { clientX: 210, pointerType: "touch" });
    expect(screen.getByRole("status").textContent).toBe("February 2026 no income");
    fireEvent.pointerMove(wrap, { clientX: 900, pointerType: "touch" });
    expect(screen.getByRole("status").textContent).toBe("March 2026 -150%"); // the true rate, not the clamped one
  });

  it("the reading stays when the finger lifts and goes when something else is pressed", () => {
    const { container } = render(<RateChart months={months} links={false} />);
    const wrap = plotOf(container);
    fireEvent.pointerDown(wrap, { clientX: 300, pointerType: "touch" });
    fireEvent.pointerUp(wrap, { clientX: 300, pointerType: "touch" });
    expect(screen.getByRole("status")).toBeTruthy();
    fireEvent.pointerDown(document.body, { clientX: 5, pointerType: "touch" });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("a drag that ends on a month's link does not open that month, but a tap does", () => {
    const { container } = render(<RateChart months={months} chosen="2026-03" />);
    const wrap = plotOf(container);
    const link = container.querySelector("a");
    fireEvent.pointerDown(link, { clientX: 100, pointerType: "touch" });
    fireEvent.pointerMove(link, { clientX: 180, pointerType: "touch" });
    fireEvent.pointerUp(link, { clientX: 180, pointerType: "touch" });
    expect(fireEvent.click(link)).toBe(false); // prevented
    fireEvent.pointerDown(link, { clientX: 100, pointerType: "touch" });
    fireEvent.pointerUp(link, { clientX: 100, pointerType: "touch" });
    expect(fireEvent.click(link)).toBe(true);
    expect(wrap).toBeTruthy();
  });

  it("a sideways drag holds the page still; an up-and-down one is left to scroll", () => {
    const { container } = render(<RateChart months={months} links={false} />);
    const wrap = plotOf(container);
    const at = (clientX, clientY) => ({ touches: [{ clientX, clientY }], cancelable: true });
    fireEvent.touchStart(wrap, at(100, 100));
    expect(fireEvent.touchMove(wrap, at(112, 103))).toBe(false); // sideways: ours
    expect(fireEvent.touchMove(wrap, at(120, 160))).toBe(false); // and it stays ours however it wanders
    fireEvent.touchStart(wrap, at(100, 100));
    expect(fireEvent.touchMove(wrap, at(103, 115))).toBe(true); // up and down: the page scrolls
    expect(fireEvent.touchMove(wrap, at(160, 120))).toBe(true);
  });

  it("while a sideways drag is under way the scrolling screen is held, and let go when the finger lifts", () => {
    const root = document.createElement("div");
    root.id = "root";
    document.body.appendChild(root);
    const { container } = render(<RateChart months={months} links={false} />, { container: root });
    const wrap = plotOf(container);
    const at = (clientX, clientY) => ({ touches: [{ clientX, clientY }], cancelable: true });
    fireEvent.touchStart(wrap, at(100, 100));
    fireEvent.touchMove(wrap, at(103, 101)); // the very first movement decides
    expect(root.style.overflowY).toBe("hidden");
    fireEvent.touchEnd(wrap, { touches: [] });
    expect(root.style.overflowY).toBe("");
    fireEvent.touchStart(wrap, at(100, 100));
    fireEvent.touchMove(wrap, at(101, 104));
    expect(root.style.overflowY).toBe(""); // an up-and-down touch holds nothing
    root.remove();
  });

  it("a finger that rests on the chart before moving holds the screen, whichever way it then moves", () => {
    vi.useFakeTimers();
    try {
      const root = document.createElement("div");
      root.id = "root";
      document.body.appendChild(root);
      const { container } = render(<RateChart months={months} links={false} />, { container: root });
      const wrap = plotOf(container);
      const at = (clientX, clientY) => ({ touches: [{ clientX, clientY }], cancelable: true });
      fireEvent.touchStart(wrap, at(100, 100));
      vi.advanceTimersByTime(200);
      expect(root.style.overflowY).toBe("hidden");
      expect(fireEvent.touchMove(wrap, at(101, 115))).toBe(false); // up and down, but it rested first
      fireEvent.touchEnd(wrap, { touches: [] });
      expect(root.style.overflowY).toBe("");
      fireEvent.touchStart(wrap, at(100, 100));
      expect(fireEvent.touchMove(wrap, at(101, 115))).toBe(true); // a quick flick still scrolls
      vi.advanceTimersByTime(200);
      expect(root.style.overflowY).toBe(""); // and is not claimed late
      root.remove();
    } finally {
      vi.useRealTimers();
    }
  });

  it("the money chart's key shows the latest month, then the month under the finger", () => {
    const { container } = render(<MoneyChart months={months} links={false} />);
    const wrap = plotOf(container);
    expect(screen.getByRole("status").textContent).toBe("March 2026");
    fireEvent.pointerDown(wrap, { clientX: 100, pointerType: "touch" });
    expect(screen.getByRole("status").textContent).toBe("January 2026");
    expect(container.querySelector(".legend").textContent).toBe("Income$5,000Spending$4,000");
    expect(container.querySelector(".tip")).toBeNull(); // nothing floats over the key
  });

  it("the chart takes no keyboard focus ring of its own", () => {
    const { container } = render(<RateChart months={months} links={false} />);
    expect(container.querySelector("svg[tabindex]")).toBeNull();
  });
});
