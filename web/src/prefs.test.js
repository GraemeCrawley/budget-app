import { describe, expect, it } from "vitest";
import { apply, clean, DEFAULTS } from "./prefs.js";

describe("prefs", () => {
  it("falls back to the defaults for anything missing or not allowed", () => {
    expect(clean(null)).toEqual(DEFAULTS);
    expect(clean({ theme: "pink", text: "large", hide: "yes" })).toEqual({ theme: "dark", text: "large", hide: false });
  });

  it("puts the choices on the root element for the stylesheet", () => {
    const root = document.createElement("div");
    apply({ theme: "light", text: "larger", hide: true }, root);
    expect(root.dataset).toMatchObject({ theme: "light", text: "larger", hide: "" });
    apply(DEFAULTS, root);
    expect(root.dataset.theme).toBe("dark");
    expect("text" in root.dataset || "hide" in root.dataset).toBe(false);
  });
});
