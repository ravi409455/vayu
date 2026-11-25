import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ConditionBuilder } from "./ConditionBuilder";

const FIELDS = [
  { value: "inspection.door", label: "Door" },
  { value: "inspection.odometer", label: "Odometer" },
];

function Harness({ initial = null as unknown }) {
  const [rule, setRule] = useState<unknown>(initial);
  return (
    <>
      <ConditionBuilder label="Show only if" value={rule} onChange={setRule} fields={FIELDS} />
      <pre data-testid="rule">{JSON.stringify(rule)}</pre>
    </>
  );
}

describe("ConditionBuilder", () => {
  it("keeps a half-finished row on screen and reports a rule once it is complete", async () => {
    const u = userEvent.setup();
    render(<Harness />);
    await u.click(screen.getByRole("button", { name: "+ Add condition" }));
    expect(screen.getByLabelText("Field")).toBeInTheDocument(); // not thrown away
    expect(screen.getByTestId("rule")).toHaveTextContent("null");
    await u.selectOptions(screen.getByLabelText("Field"), "inspection.door");
    await u.type(screen.getByLabelText("Value"), "dent");
    expect(JSON.parse(screen.getByTestId("rule").textContent!)).toEqual({ "==": [{ var: "inspection.door" }, "dent"] });
  });
  it("shows an existing rule as rows and joins several with and / or", async () => {
    const u = userEvent.setup();
    render(<Harness initial={{ "==": [{ var: "inspection.door" }, "dent"] }} />);
    expect(screen.getByLabelText("Value")).toHaveValue("dent");
    await u.click(screen.getByRole("button", { name: "+ Add condition" }));
    await u.selectOptions(screen.getAllByLabelText("Field")[1]!, "inspection.odometer");
    await u.selectOptions(screen.getAllByLabelText("Operator")[1]!, ">");
    await u.type(screen.getAllByLabelText("Value")[1]!, "100");
    await u.selectOptions(screen.getByLabelText("Join"), "or");
    const rule = JSON.parse(screen.getByTestId("rule").textContent!);
    expect(Object.keys(rule)).toEqual(["or"]);
    expect(rule.or).toHaveLength(2);
  });
  it("removing the last condition means always", async () => {
    const u = userEvent.setup();
    render(<Harness initial={{ "!!": [{ var: "inspection.door" }] }} />);
    await u.click(screen.getByRole("button", { name: "Remove condition" }));
    expect(screen.getByTestId("rule")).toHaveTextContent("null");
    expect(screen.getByText(/Always/)).toBeInTheDocument();
  });
  it("a rule it cannot draw stays as editable JSON and loses nothing", async () => {
    const rule = { some: [{ var: "_defects" }, { in: [{ var: "" }, ["inspection.door"]] }] };
    render(<Harness initial={rule} />);
    expect(screen.getByLabelText("Show only if JSON")).toHaveValue(JSON.stringify(rule, null, 1));
    expect(screen.queryByRole("button", { name: "Use the simple builder" })).toBeNull();
  });
});
