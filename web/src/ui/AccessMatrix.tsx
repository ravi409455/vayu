import { STAGE_LABEL } from "../api/labels";
import type { Access } from "../api/types";
import { getCell, LEVELS, ROLES, setCell, setRole, STAGES, type Level } from "../lib/access";


/** Who sees or edits this at each stage. "—" means not decided here: the section, page or default applies. */
export function AccessMatrix({ value, onChange }: { value: Access; onChange: (a: Access) => void }) {
  return (
    <table className="access-grid" aria-label="Access by role and stage">
      <thead><tr><th>Role</th>{STAGES.map((s) => <th key={s}>{STAGE_LABEL[s]}</th>)}<th>All</th></tr></thead>
      <tbody>
        {ROLES.map((r) => (
          <tr key={r}>
            <td>{r}</td>
            {STAGES.map((s) => (
              <td key={s}>
                <select aria-label={`${r} ${STAGE_LABEL[s]}`} value={getCell(value, r, s)} onChange={(e) => onChange(setCell(value, r, s, e.target.value as Level | ""))}>
                  <option value="">—</option>
                  {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </td>
            ))}
            <td>
              <select aria-label={`${r} all stages`} value="" onChange={(e) => e.target.value !== "?" && onChange(setRole(value, r, e.target.value as Level | ""))}>
                <option value="?">set all…</option>
                <option value="">clear</option>
                {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
