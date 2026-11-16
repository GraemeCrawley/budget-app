import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { get } from "../api.js";
import CategoryPicker from "./CategoryPicker.jsx";

vi.mock("../api.js", () => ({ get: vi.fn() }));

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue({ categories: ["Coffee", "Gifts"], blocks: { Coffee: "Food", Gifts: "Everything else" } });
});

describe("CategoryPicker", () => {
  it("folds the categories into groups, opens the one holding the current category, and picks from it", async () => {
    get.mockResolvedValue({
      categories: ["Clothes", "Coffee", "Pottery", "Rent", "Subscriptions", "Transport"],
      blocks: { Clothes: "Everything else", Coffee: "Food", Pottery: "Everything else", Rent: "Bills",
        Subscriptions: "Subscriptions", Transport: "Everything else" },
    });
    const onPick = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<CategoryPicker value="Rent" onPick={onPick} />);
    await screen.findByText("Food");
    const groups = [...container.querySelectorAll("details")];
    expect(groups.map((g) => [g.querySelector("summary").textContent, g.open])).toEqual([
      ["Food1", false], ["Bills2", true], ["Shopping1", false], ["Travel & transport1", false], ["Other1", false]]);
    expect(screen.getByText("Coffee")).not.toBeVisible();
    await user.click(screen.getByText("Shopping"));
    await user.click(screen.getByRole("button", { name: "Clothes" }));
    expect(onPick).toHaveBeenCalledWith("Clothes");
  });

  it("keeps therapy, eye care and the other health categories together under Health", async () => {
    const names = ["Eye care", "Medical & dental", "Personal care", "Pharmacy", "Therapy"];
    get.mockResolvedValue({ categories: names, blocks: Object.fromEntries(names.map((n) => [n, "Everything else"])) });
    const { container } = render(<CategoryPicker value="Therapy" onPick={() => {}} />);
    await screen.findByText("Health");
    const open = [...container.querySelectorAll("details")].filter((d) => d.open);
    expect(open).toHaveLength(1);
    expect([...open[0].querySelectorAll("button")].map((b) => b.textContent.replace(" (current)", ""))).toEqual(names);
  });

  it("has a New category row at the bottom, which opens a name field", async () => {
    const user = userEvent.setup();
    render(<CategoryPicker value={null} onPick={() => {}} />);
    const rows = await screen.findAllByRole("button");
    expect(rows[rows.length - 1]).toHaveTextContent("New category");
    await user.click(rows[rows.length - 1]);
    const input = screen.getByLabelText("Name");
    expect(input).toHaveAttribute("maxlength", "40");
    expect(input).toHaveAttribute("autocapitalize", "sentences");
  });

  it("keeps Use this disabled for an empty name, then picks the trimmed name", async () => {
    const onPick = vi.fn();
    const user = userEvent.setup();
    render(<CategoryPicker value={null} onPick={onPick} />);
    await user.click(await screen.findByRole("button", { name: /New category/ }));
    const use = screen.getByRole("button", { name: "Use this" });
    expect(use).toBeDisabled();
    await user.type(screen.getByLabelText("Name"), "   ");
    expect(use).toBeDisabled();
    await user.type(screen.getByLabelText("Name"), "  Pottery ");
    await user.click(use);
    expect(onPick).toHaveBeenCalledWith("Pottery");
  });

  it("Cancel goes back to the list without picking", async () => {
    const onPick = vi.fn();
    const user = userEvent.setup();
    render(<CategoryPicker value={null} onPick={onPick} />);
    await user.click(await screen.findByRole("button", { name: /New category/ }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New category/ })).toBeInTheDocument();
    expect(onPick).not.toHaveBeenCalled();
  });
});
