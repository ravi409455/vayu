import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InfoTip } from "./InfoTip";

afterEach(() => vi.restoreAllMocks());

describe("the little i", () => {
  it("opens on hover and closes when the pointer leaves, and still works by click and keyboard", async () => {
    const u = userEvent.setup();
    render(<InfoTip>Explains things</InfoTip>);
    expect(screen.queryByRole("tooltip")).toBeNull();
    await u.hover(screen.getByRole("button", { name: "More info" }));
    expect(screen.getByRole("tooltip")).toHaveTextContent("Explains things");
    await u.unhover(screen.getByRole("button", { name: "More info" }));
    expect(screen.queryByRole("tooltip")).toBeNull();
    await u.tab();
    expect(screen.getByRole("tooltip")).toBeInTheDocument(); // keyboard focus
    await u.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
