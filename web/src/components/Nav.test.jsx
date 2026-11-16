import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import Nav from "./Nav.jsx";

describe("Nav", () => {
  it("has Home, Months, Plan and Add, marks the current one, and shows the version under the bar", () => {
    render(<Nav route="block" />);
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect([...nav.children].map((el) => el.textContent)).toEqual(["Home", "Months", "Plan", "Add"]);
    expect(screen.getByRole("link", { name: "Months" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText(/^Version .+, \d\d:\d\d$/)).toBeInTheDocument();
  });
});
