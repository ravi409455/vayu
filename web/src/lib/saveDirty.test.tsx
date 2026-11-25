import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { StaleDialog } from "../ui/StaleDialog";
import { saveDirty } from "./saveDirty";

afterEach(() => vi.restoreAllMocks());

describe("409 'changed by someone': retry only my own fields", () => {
  const stale = new ApiError(409, {
    code: "STALE_INSPECTION",
    detail: "x",
    changed_by: "priya",
    changed_at: "2026-11-23T10:00:00Z",
    changed_keys: ["remarks"],
    row_version: 7,
  });

  it("turns the 409 into data, sends only the changed fields, and retries with the new version", async () => {
    const send = vi.fn().mockRejectedValueOnce(stale).mockResolvedValueOnce({ ok: 1 });
    const mine = { odometer: 150 };
    const first = await saveDirty(send, 3, mine);
    expect(first).toEqual({ ok: false, stale: { by: "priya", at: "2026-11-23T10:00:00Z", keys: ["remarks"], rowVersion: 7 } });
    const second = await saveDirty(send, first.ok ? 0 : first.stale.rowVersion, mine);
    expect(second.ok).toBe(true);
    expect(send).toHaveBeenNthCalledWith(1, 3, { odometer: 150 });
    expect(send).toHaveBeenNthCalledWith(2, 7, { odometer: 150 }); // only my field, on the newest version
  });
  it("other failures are not swallowed", async () => {
    await expect(saveDirty(vi.fn().mockRejectedValue(new ApiError(400, { detail: "bad" })), 1, {})).rejects.toBeInstanceOf(ApiError);
    await expect(saveDirty(vi.fn().mockRejectedValue(new ApiError(409, { code: "DRAFT_EXISTS" })), 1, {})).rejects.toBeInstanceOf(ApiError);
  });
  it("the dialog names who changed it and warns when both changed the same field", async () => {
    const onRetry = vi.fn();
    const u = userEvent.setup();
    render(
      <StaleDialog
        info={{ by: "priya", at: "", keys: ["remarks", "odometer"], rowVersion: 7 }}
        mine={["odometer"]}
        onRetry={onRetry}
        onReload={() => {}}
      />,
    );
    expect(screen.getByRole("dialog", { name: /priya changed this/ })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("odometer");
    await u.click(screen.getByRole("button", { name: /Save only my 1 change/ }));
    expect(onRetry).toHaveBeenCalled();
  });
  it("no warning when the changes do not overlap", () => {
    render(
      <StaleDialog
        info={{ by: "priya", at: "", keys: ["remarks"], rowVersion: 7 }}
        mine={["odometer", "city"]}
        onRetry={() => {}}
        onReload={() => {}}
      />,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: /Save only my 2 changes/ })).toBeInTheDocument();
  });
});
