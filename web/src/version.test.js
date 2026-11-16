import { describe, expect, it } from "vitest";
import { BUILT, versionWords } from "./version.js";

describe("version", () => {
  it("is the build moment as a day and a time", () => {
    expect(versionWords("2026-11-15T12:05:00")).toMatch(/^(Nov\.? 15|15 Nov\.?), 12:05$/);
  });
  it("says unknown rather than a broken date", () => {
    expect(versionWords(null)).toBe("unknown");
    expect(versionWords("nonsense")).toBe("unknown");
  });
  it("every build carries its moment", () => {
    expect(Number.isNaN(new Date(BUILT).getTime())).toBe(false);
  });
});
