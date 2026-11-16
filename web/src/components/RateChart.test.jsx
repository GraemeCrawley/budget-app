import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import RateChart, { chartScale } from "./RateChart.jsx";

const m = (month, savings_rate) => ({ month, savings_rate });

describe("RateChart", () => {
  it("each other month is a link to that month, and a month with no rate still is", () => {
    const { container } = render(
      <RateChart months={[m("2026-01", 0.2), m("2026-02", null), m("2026-03", 0.3)]} chosen="2026-03" />);
    const links = [...container.querySelectorAll("a")];
    expect(links.map((a) => [a.getAttribute("href"), a.getAttribute("aria-label")])).toEqual([
      ["#/month/2026-01", "January 2026"], ["#/month/2026-02", "February 2026"]]);
  });

  it("draws a dot for each month with a rate and skips a month with none", () => {
    const { container } = render(
      <RateChart months={[m("2026-01", 0.2), m("2026-02", null), m("2026-03", 0.3)]} chosen="2026-03" />);
    const dots = container.querySelectorAll("circle");
    expect(dots).toHaveLength(2);
    expect([...dots].map((d) => d.getAttribute("r"))).toEqual(["3", "5"]);
    expect(container.textContent).toContain("Feb"); // the month keeps its place on the axis
  });

  it("keeps the axis inside -100% to 100% and flags an extreme month", () => {
    const { domain, ticks, clamped } = chartScale([-630, 20, 30, 67]);
    expect(domain[0]).toBeGreaterThanOrEqual(-100);
    expect(domain[1]).toBeLessThanOrEqual(100);
    expect(Math.abs(domain[0] % 25)).toBe(0);
    expect(domain[1] % 25).toBe(0);
    expect(ticks).toContain(0);
    expect(new Set(ticks).size).toBe(ticks.length);
    expect(ticks.every((t) => t >= domain[0] && t <= domain[1])).toBe(true);
    expect(clamped).toEqual([true, false, false, false]);
  });

  it("always includes zero in the domain", () => {
    const { domain, ticks } = chartScale([20, 30]);
    expect(domain[0]).toBe(0);
    expect(domain[1]).toBe(50);
    expect(ticks).toContain(0);
  });

  it("draws an extreme month at the edge with a hollow marker and names it under the chart", () => {
    const { container } = render(
      <RateChart months={[m("2026-01", -6.3), m("2026-02", 0.2), m("2026-03", 0.3)]} chosen="2026-03" />);
    const dots = [...container.querySelectorAll("circle")];
    expect(dots).toHaveLength(3);
    expect(dots.filter((d) => d.getAttribute("fill") === "var(--surface)")).toHaveLength(1);
    expect(container.textContent).toContain("January is off the chart (-630%).");
    const labels = [...container.querySelectorAll(".recharts-yAxis-tick-labels .recharts-cartesian-axis-tick-value")]
      .map((t) => t.textContent);
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels).toContain("0%");
  });

  it("counts several extreme months in one line", () => {
    const { container } = render(
      <RateChart months={[m("2026-01", -6.3), m("2026-02", 1.4), m("2026-03", 0.3)]} chosen="2026-03" />);
    expect(container.textContent).toContain("2 months are off the chart.");
    expect(container.textContent).not.toContain("is off the chart");
  });

  it("says nothing when every month fits", () => {
    const { container } = render(<RateChart months={[m("2026-01", 0.2), m("2026-02", -1)]} chosen="2026-02" />);
    expect(container.textContent).not.toContain("off the chart");
  });

  it("shows about six month labels for twelve months, ending on the last", () => {
    const months = Array.from({ length: 12 }, (_, i) => m(`2025-${String(i + 1).padStart(2, "0")}`, 0.2));
    const { container } = render(<RateChart months={months} chosen="2025-12" />);
    const labels = [...container.querySelectorAll(".recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-value")]
      .map((t) => t.textContent);
    expect(labels.length).toBeLessThanOrEqual(6);
    expect(labels.length).toBeGreaterThanOrEqual(4);
    expect(labels.at(-1)).toBe("Dec");
  });
});
