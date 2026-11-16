import { describe, expect, it } from "vitest";
import { dollars, exact, monthName, longDate, percent, shortDate } from "./money.js";

describe("money", () => {
  it("formats whole dollars with the minus sign before the $", () => {
    expect(dollars(123456)).toBe("$1,235");
    expect(dollars(-450)).toBe("-$5");
    expect(dollars(0)).toBe("$0");
  });
  it("formats exact amounts to the cent", () => {
    expect(exact(-450)).toBe("-$4.50");
    expect(exact(123456)).toBe("$1,234.56");
  });
  it("formats a rate as a whole percent, and no rate as a dash", () => {
    expect(percent(0.2345)).toBe("23%");
    expect(percent(null)).toBe("–");
  });
  it("names months and short dates", () => {
    expect(monthName("2026-01")).toBe("January 2026");
    expect(shortDate("2026-01-05")).toBe("Jan 5");
    expect(longDate("2026-07-18")).toBe("Jul 18, 2026");
  });
});
