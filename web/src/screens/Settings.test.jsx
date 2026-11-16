import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Settings from "./Settings.jsx";

vi.mock("../components/Reminders.jsx", () => ({ default: () => null }));

describe("Settings", () => {
  it("shows each choice with the current one pressed, and reports a new choice", async () => {
    const setPref = vi.fn();
    render(<Settings prefs={{ theme: "dark", text: "normal", hide: false }} setPref={setPref} />);
    const theme = screen.getByRole("group", { name: "Theme" });
    expect(within(theme).getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(theme).getByRole("button", { name: "Light" }));
    expect(setPref).toHaveBeenCalledWith("theme", "light");
    await userEvent.click(screen.getByRole("button", { name: "Hidden" }));
    expect(setPref).toHaveBeenCalledWith("hide", true);
    expect(screen.getByRole("link", { name: "Open Plan" })).toHaveAttribute("href", "#/plan");
    expect(screen.getByText(/^Version .+, \d\d:\d\d$/)).toBeInTheDocument();
  });
});
