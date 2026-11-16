import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { go, parse, useRoute } from "./router.js";

describe("router", () => {
  it("parses every route from the hash", () => {
    location.hash = "#/block/2026-01/Food";
    expect(parse(location.hash)).toEqual({ name: "block", params: { ym: "2026-01", block: "Food" } });
    expect(parse("#/")).toEqual({ name: "home", params: {} });
    expect(parse("")).toEqual({ name: "home", params: {} });
    expect(parse("#/month/2026-03")).toEqual({ name: "month", params: { ym: "2026-03" } });
    expect(parse("#/months")).toEqual({ name: "months", params: {} });
    expect(parse("#/charge/17")).toEqual({ name: "charge", params: { id: "17" } });
    expect(parse("#/add")).toEqual({ name: "add", params: {} });
    expect(parse("#/review/2026-01")).toEqual({ name: "review", params: { ym: "2026-01" } });
    expect(parse("#/review")).toEqual({ name: "review", params: {} });
    expect(parse("#/settings")).toEqual({ name: "settings", params: {} });
  });
  it("decodes a block name with a space", () => {
    expect(parse("#/block/2026-01/Big%20purchases").params.block).toBe("Big purchases");
  });
  it("sends anything it does not know to home", () => {
    expect(parse("#/nonsense")).toEqual({ name: "home", params: {} });
    expect(parse("#/month/nope")).toEqual({ name: "home", params: {} });
  });
  it("follows the hash as it changes", async () => {
    location.hash = "#/";
    const { result } = renderHook(() => useRoute());
    expect(result.current.name).toBe("home");
    await act(async () => {
      go("#/add");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(result.current).toEqual({ name: "add", params: {} });
  });
});
