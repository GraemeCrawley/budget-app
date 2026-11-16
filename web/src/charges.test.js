import { beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "./api.js";
import { biggest, monthCharges } from "./charges.js";

vi.mock("./api.js", () => ({ get: vi.fn() }));
beforeEach(() => { get.mockReset(); get.mockResolvedValue({ transactions: [] }); });

describe("monthCharges", () => {
  it("asks once when two parts of a screen want the same month together, and again later", async () => {
    await Promise.all([monthCharges("2026-02"), monthCharges("2026-02")]);
    expect(get).toHaveBeenCalledTimes(1);
    await monthCharges("2026-02");
    expect(get).toHaveBeenCalledTimes(2);
  });
});

describe("biggest", () => {
  it("is the largest money out, biggest first, leaving out refunds and anything not spending", () => {
    const t = (id, amount_cents, block = "Food") => ({ id, amount_cents, block });
    expect(biggest([t(1, -500), t(2, -90000), t(3, 70000), t(4, -800000, null), t(5, -2000)], 2).map((x) => x.id))
      .toEqual([2, 5]);
  });
});
