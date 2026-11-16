import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as push from "../push.js";
import Reminders from "./Reminders.jsx";

vi.mock("../push.js", () => ({
  support: vi.fn(), state: vi.fn(), turnOn: vi.fn(), turnOff: vi.fn(), sendTest: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  push.support.mockReturnValue("ok");
});

describe("Reminders", () => {
  it("offers to turn reminders on, and then to send a test", async () => {
    push.state.mockResolvedValueOnce({ on: false, phones: 0, last: null })
      .mockResolvedValue({ on: true, phones: 1, last: null });
    push.turnOn.mockResolvedValue();
    render(<Reminders />);
    await userEvent.click(await screen.findByRole("button", { name: "Turn on reminders on this phone" }));
    expect(push.turnOn).toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Send a test reminder" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Reminders are on for this phone.");
    expect(screen.getByText("No reminder has been sent yet.")).toBeInTheDocument();
  });

  it("says why when the phone refuses", async () => {
    push.state.mockResolvedValue({ on: false, phones: 0, last: null });
    push.turnOn.mockRejectedValue(new Error("Notifications are turned off for this app in the phone's settings."));
    render(<Reminders />);
    await userEvent.click(await screen.findByRole("button", { name: "Turn on reminders on this phone" }));
    expect(await screen.findByRole("status")).toHaveTextContent("turned off for this app");
  });

  it("says when the last one was sent and whether it was opened", async () => {
    push.state.mockResolvedValue({ on: true, phones: 1,
      last: { kind: "reminder", sent_at: "2026-11-01T07:00:02-05:00", delivered_at: null, opened_at: "2026-11-01T07:14:40-05:00" } });
    render(<Reminders />);
    expect(await screen.findByText("Last reminder sent Nov 1, 07:00: opened Nov 1, 07:14.")).toBeInTheDocument();
  });

  it("explains the home-screen step in an iPhone browser tab, with no button", async () => {
    push.support.mockReturnValue("home-screen");
    push.state.mockResolvedValue({ on: false, phones: 0, last: null });
    render(<Reminders />);
    expect(await screen.findByText(/add this app to the home screen/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
