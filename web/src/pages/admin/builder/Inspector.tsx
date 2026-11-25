import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { Access, FormPage, FormSection } from "../../../api/types";
import { AccessEditor } from "../../../ui/AccessEditor";
import { ConditionBuilder, type FieldChoice } from "../../../ui/ConditionBuilder";
import { Check, Field, Tabs } from "../../../ui/kit";
import { LibraryBox } from "./LibraryBox";

type Pane = "settings" | "logic" | "access";

/** Settings for a page or a section (a field has its own editor). */
export function ContainerEditor({
  kind,
  item,
  pages,
  choices,
  formKind,
  parentAccess,
  readOnly,
  onSave,
  onDelete,
  onMove,
  onChanged,
}: {
  kind: "page" | "section";
  item: FormPage | FormSection;
  pages: FormPage[];
  choices: FieldChoice[];
  formKind: string;
  parentAccess?: Access;
  readOnly: boolean;
  onSave: (b: Record<string, unknown>) => void;
  onDelete: () => void;
  onMove: (pageId: number) => void;
  onChanged: () => void;
}) {
  const make = () => ({
    title: item.title,
    visible: item.visible,
    show_if: item.show_if,
    access: item.access,
    gate: "gate" in item ? item.gate : false,
  });
  const [d, setD] = useState(make);
  const [pane, setPane] = useState<Pane>("settings");
  useEffect(() => setD(make()), [item.id, item.title, item.visible, item.show_if, item.access, "gate" in item && item.gate]); // eslint-disable-line react-hooks/exhaustive-deps -- resets the draft only when the saved values change, not for a new object with the same values
  const locked = "locked" in item && item.locked;
  const dirty = JSON.stringify(d) !== JSON.stringify(make());
  const section = kind === "section" ? (item as FormSection) : null;
  return (
    <div>
      <div className="insp-head">
        <div className="grow">
          <h2>{item.title}</h2>
          <p className="muted small">{kind === "page" ? "Page" : "Section"}</p>
        </div>
      </div>
      <Tabs
        value={pane}
        onChange={setPane}
        tabs={[
          { id: "settings", label: "Settings" },
          { id: "logic", label: "Logic" },
          { id: "access", label: "Access" },
        ]}
      />
      <fieldset disabled={readOnly || locked} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        {pane === "settings" && (
          <>
            <Field label="Title">
              <input value={d.title} disabled={locked} onChange={(e) => setD({ ...d, title: e.target.value })} />
            </Field>
            {kind === "page" && (
              <Check
                label="Must be finished before moving on"
                checked={d.gate}
                onChange={(e) => setD({ ...d, gate: e.target.checked })}
                tip="People cannot go to the next page until every required field here is filled. Use it for steps like check-in that must be done first."
              />
            )}
            {section && (
              <Field label="Move to page">
                <select aria-label="Move to page" value={section.page} onChange={(e) => onMove(Number(e.target.value))}>
                  {pages.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title}
                    </option>
                  ))}
                </select>
              </Field>
            )}
          </>
        )}
        {pane === "logic" && (
          <>
            <label className="check">
              <input type="checkbox" checked={d.visible} onChange={(e) => setD({ ...d, visible: e.target.checked })} /> Visible
            </label>
            <ConditionBuilder label="Show only if" value={d.show_if} onChange={(r) => setD({ ...d, show_if: r })} fields={choices} />
          </>
        )}
        {pane === "access" && (
          <>
            <AccessEditor
              note={`What you set here applies to everything in this ${kind}, unless a field sets its own.`}
              value={d.access}
              onChange={(a) => setD({ ...d, access: a })}
              kind={formKind}
              parents={{ page: parentAccess }}
            />
          </>
        )}
      </fieldset>
      {section && <LibraryBox kind="section" id={section.id} library={section.library} readOnly={readOnly} onDone={onChanged} />}
      {!readOnly && (
        <div className="insp-foot">
          <button className="primary" disabled={!dirty} onClick={() => onSave(d)}>
            Save {kind}
          </button>
          <button className="danger" onClick={onDelete}>
            <Trash2 size={14} aria-hidden /> Delete {kind}
          </button>
        </div>
      )}
    </div>
  );
}
