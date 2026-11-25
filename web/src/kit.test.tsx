import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Confirm, Field, Modal, ToastProvider, useToast } from "./ui/kit";

afterEach(() => vi.useRealTimers());

describe("dialogs (H-19)", () => {
  function Opener() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>Open it</button>
        {open && (
          <Modal title="Name it" onClose={() => setOpen(false)}>
            <input aria-label="Name" />
          </Modal>
        )}
      </>
    );
  }
  it("moves focus in, closes on Escape, and gives focus back", async () => {
    render(<Opener />);
    const opener = screen.getByRole("button", { name: "Open it" });
    await userEvent.setup().click(opener);
    expect(screen.getByRole("dialog", { name: "Name it" })).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveFocus();
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true })); // what Escape fires on a modal dialog
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });
  it("a click beside a dialog with inputs does not close it (and lose what was typed)", async () => {
    render(<Opener />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Open it" }));
    fireEvent.click(screen.getByRole("dialog"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("Confirm sends once (F-112)", () => {
  it("a double click while the action runs sends it once", async () => {
    let done!: () => void;
    const act1 = vi.fn(
      () =>
        new Promise<void>((r) => {
          done = r;
        }),
    );
    render(
      <Confirm title="Go?" onConfirm={act1} onCancel={() => {}}>
        x
      </Confirm>,
    );
    const u = userEvent.setup();
    await u.dblClick(screen.getByRole("button", { name: "Confirm" }));
    expect(act1).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    await act(async () => done());
    expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
  });
  it("busy keeps the button disabled", () => {
    render(
      <Confirm title="Go?" busy onConfirm={() => {}} onCancel={() => {}}>
        x
      </Confirm>,
    );
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  });
});

describe("toasts (F-184, F-032)", () => {
  function Say() {
    const { say } = useToast();
    return (
      <>
        <button onClick={() => say("Saved.")}>ok</button>
        <button onClick={() => say("Could not save", true)}>bad</button>
      </>
    );
  }
  it("an error stays until closed and is announced at once; good news fades", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Say />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("ok"));
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    fireEvent.click(screen.getByText("bad"));
    act(() => {
      vi.advanceTimersByTime(10_000);
    }); // the first toast's timer does not take the error away
    expect(screen.getByRole("alert")).toHaveTextContent("Could not save");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("form fields (F-179)", () => {
  it("the input points at its help and error text and says it is wrong", () => {
    render(
      <Field label="Phone" help="10 digits" error="Too short">
        <input />
      </Field>,
    );
    const input = screen.getByLabelText("Phone");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("10 digits Too short");
  });
});
