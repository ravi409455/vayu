import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FormField } from "../api/types";
import { AnswerValue } from "./AnswerSheet";

describe("one meaning of an empty answer (F-029)", () => {
  it("an answer of only spaces reads as not answered, as the rules treat it", () => {
    const f = { key: "note", type: "short_text", label: "Note", config: {} } as unknown as FormField;
    render(<AnswerValue f={f} v="   " />);
    expect(screen.getByText("Not answered")).toBeInTheDocument();
  });
});
