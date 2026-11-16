import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ErrorBoundary from "./ErrorBoundary.jsx";

function Broken() {
  throw new TypeError("cannot destructure null");
}

afterEach(() => vi.restoreAllMocks());

describe("ErrorBoundary", () => {
  it("shows the plain problem text and a reload button instead of a blank page", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    const reload = vi.fn();
    render(<ErrorBoundary onReload={reload}><Broken /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this. Try again.");
    await userEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(reload).toHaveBeenCalledOnce();
    expect(logged).toHaveBeenCalled(); // React reports the caught error; kept out of the test output
  });

  it("renders its children when nothing throws", () => {
    render(<ErrorBoundary><p>fine</p></ErrorBoundary>);
    expect(screen.getByText("fine")).toBeInTheDocument();
  });
});
