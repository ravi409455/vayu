import { Eye, EyeOff, Pencil } from "lucide-react";
import type { Access } from "../api/types";
import { defaultLevel, effectiveLevel, getCell, PRESETS, ROLES, setCell, STAGES, type Level, type LevelSource } from "../lib/access";
import { InfoTip } from "./InfoTip";

const STAGE: Record<string, { label: string; tip: string }> = {
  draft: { label: "Not assigned", tip: "The booking exists but no expert has it yet." },
  assigned: { label: "Assigned", tip: "An expert has the job but has not started." },
  in_progress: { label: "Working", tip: "The expert is doing the inspection." },
  submitted: { label: "Submitted", tip: "The expert submitted; photos are still uploading." },
  completed: { label: "Completed", tip: "Everything arrived and the report was made." },
  cancelled: { label: "Cancelled", tip: "The booking was cancelled." },
};
const ICON = { hidden: EyeOff, view: Eye, edit: Pencil };
const WORD: Record<Level, string> = { hidden: "Hidden", view: "Can see", edit: "Can edit" };
const NEXT: Record<string, Level | ""> = { "": "hidden", hidden: "view", view: "edit", edit: "" };
const FROM: Record<LevelSource, string> = { field: "set on this field", section: "from its section", page: "from its page", default: "the standard rule" };

/** Who can see or edit this, at each stage of a booking. One row per stage, one column per role,
 *  so it always fits on screen. Each cell shows the result that applies (nobody has to guess); a
 *  faded cell is inherited, a solid one is set right here. Click a cell to cycle
 *  inherited → hidden → can see → can edit. */
export function AccessEditor({ value, onChange, kind, ftype = "short_text", parents = {}, disabled }: {
  value: Access; onChange: (a: Access) => void; kind: string; ftype?: string; parents?: { section?: Access; page?: Access }; disabled?: boolean;
}) {
  const matches = (p: (typeof PRESETS)[number]) => JSON.stringify(p.apply()) === JSON.stringify(value ?? {});
  return (
    <div className="access">
      <div className="bar" style={{ marginBottom: 8 }}>
        <strong>Quick setup</strong>
        <InfoTip>Pick a ready-made rule, or click individual cells below. “Standard” means: experts fill it while working and can read it later; Ops can always edit.</InfoTip>
      </div>
      <div className="seg" role="group" aria-label="Quick setup" style={{ marginBottom: 14, flexWrap: "wrap" }}>
        {PRESETS.map((p) => <button key={p.id} type="button" disabled={disabled} title={p.tip} aria-pressed={matches(p)} onClick={() => onChange(p.apply() ?? {})}>{p.label}</button>)}
      </div>
      <table className="access-grid vertical" aria-label="Access by stage and role">
        <thead><tr><th>Booking stage</th>{ROLES.map((r) => <th key={r}>{r === "expert" ? "Expert" : "Ops"}</th>)}</tr></thead>
        <tbody>
          {STAGES.map((stage) => (
            <tr key={stage}>
              <th scope="row">{STAGE[stage]!.label}<InfoTip>{STAGE[stage]!.tip}</InfoTip></th>
              {ROLES.map((role) => {
                const own = getCell(value, role, stage);
                const eff = effectiveLevel(role, stage, kind, ftype, { field: value, section: parents.section, page: parents.page });
                const Icon = ICON[eff.level];
                return (
                  <td key={role}>
                    <button type="button" className={`cell ${eff.level}${own ? " own" : ""}`} disabled={disabled} aria-label={`${role} ${STAGE[stage]!.label}: ${WORD[eff.level]}`}
                      title={`${WORD[eff.level]} (${FROM[eff.source]}). Click to change.`}
                      onClick={() => onChange(setCell(value, role, stage, NEXT[own] ?? ""))}>
                      <Icon size={14} aria-hidden /><span>{WORD[eff.level]}</span>
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">Solid = set here. Faded = {kind === "booking" ? "the standard rule" : "inherited from the section, the page or the standard rule"}. Experts never see ratings or Key Checks.</p>
      <button type="button" className="link" disabled={disabled || Object.keys(value ?? {}).length === 0} onClick={() => onChange({})}>Reset to inherited</button>
      <span className="muted small"> · with nothing set an expert who is working gets: {WORD[defaultLevel("expert", "in_progress", kind, ftype)]}</span>
    </div>
  );
}
