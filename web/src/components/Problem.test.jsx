import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { reloadPage } from "../reload.js";
import Problem from "./Problem.jsx";

vi.mock("../reload.js", () => ({ reloadPage: vi.fn() }));

const failure = (status, detail = "not signed in") => Object.assign(new Error(detail), { status, detail });

beforeEach(() => reloadPage.mockReset());

describe("Problem", () => {
  it("with status 0 says the app could not be reached and that the sign-in may have expired", async () => {
    const retry = vi.fn();
    render(<Problem error={failure(0, "could not reach the server")} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't reach the app. Your sign-in may have expired.");
    expect(screen.queryByText("Your sign-in has expired.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(reloadPage).toHaveBeenCalledOnce();
    expect(retry).not.toHaveBeenCalled();
  });

  for (const status of [401]) {
    it(`with status ${status} says the sign-in has expired and offers to sign in again, not a retry`, async () => {
      const retry = vi.fn();
      render(<Problem error={failure(status)} onRetry={retry} message="Couldn't save that. Try again." retryLabel="Try again" />);
      expect(screen.getByRole("alert")).toHaveTextContent("Your sign-in has expired.");
      expect(screen.queryByText("Couldn't save that. Try again.")).not.toBeInTheDocument();
      expect(screen.queryByText(/The server said/)).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Sign in again" }));
      expect(reloadPage).toHaveBeenCalledOnce();
      expect(retry).not.toHaveBeenCalled();
    });
  }

  it("with any other status keeps its message and its retry", async () => {
    const retry = vi.fn();
    render(<Problem error={failure(500, "request failed (500)")} onRetry={retry} />);
    expect(screen.getByText("Couldn't load this. Try again.")).toBeInTheDocument();
    expect(screen.queryByText("Your sign-in has expired.")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
