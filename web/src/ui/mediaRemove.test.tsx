import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FormField, FormPage } from "../api/types";

const discard = vi.fn(async (_id: string) => {});
vi.mock("../lib/uploadManager", () => ({ addFile: vi.fn(), discardFile: (id: string) => discard(id), useUploads: () => [] }));
import { FormRenderer } from "./FormRenderer";

const selfie: FormField = {
  id: 1, key: "selfie", label: "Selfie", type: "photo", required: true, visible: true, helper_text: "", config: { max_count: 1, capture: "camera" },
  show_if: null, required_if: null, access: {}, order: 0, is_system: true, library: null,
} as unknown as FormField;
const page = { id: 1, title: "P", order: 0, visible: true, gate: false, show_if: null, access: {}, sections: [{ id: 1, page: 1, title: "S", order: 0, visible: true, show_if: null, access: {}, fields: [selfie], locked: false, library: null }] } as unknown as FormPage;

const show = (values: Record<string, unknown>, extra: Record<string, unknown> = {}, onChange = vi.fn()) =>
  render(<QueryClientProvider client={new QueryClient()}><FormRenderer kind="ops" tree={{ pages: [page], checks: [] }} values={values} onChange={onChange} bookingId="b1" {...extra} /></QueryClientProvider>);

describe("taking a photo back", () => {
  beforeEach(() => discard.mockClear());
  it("Remove also tells the server, so a retake is not refused as 'too many'", async () => {
    const onChange = vi.fn();
    show({ selfie: ["m1"] }, {}, onChange);
    await userEvent.setup().click(screen.getByRole("button", { name: "Remove" }));
    expect(onChange).toHaveBeenCalledWith("selfie", []);
    expect(discard).toHaveBeenCalledWith("m1");
  });
  it("in the builder's preview nothing is sent anywhere", async () => {
    show({ selfie: ["preview-1-0"] }, { preview: true, bookingId: undefined });
    await userEvent.setup().click(screen.getByRole("button", { name: "Remove" }));
    expect(discard).not.toHaveBeenCalled();
  });
});
