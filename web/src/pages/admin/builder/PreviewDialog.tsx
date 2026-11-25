import { Lock, Monitor, Smartphone } from "lucide-react";
import { useMemo, useState } from "react";
import { STAGE_LABEL } from "../../../api/labels";
import type { FormPage, FormVersion } from "../../../api/types";
import { effectiveLevel, STAGES } from "../../../lib/access";
import { pageGaps, visiblePages, type Answers, type Kind } from "../../../lib/formSpec";
import { FormRenderer } from "../../../ui/FormRenderer";
import { Modal } from "../../../ui/kit";

/** What a person would see: pick a role and a stage, click through the pages, and try the rules.
 *  Nothing is saved, uploaded or located. */
export function PreviewDialog({ tree, kind, onClose }: { tree: Pick<FormVersion, "pages" | "checks">; kind: Kind; onClose: () => void }) {
  const [role, setRole] = useState<"expert" | "ops">("expert");
  const [stage, setStage] = useState("in_progress");
  const [device, setDevice] = useState<"phone" | "desktop">("phone");
  const [values, setValues] = useState<Answers>({});
  const [step, setStep] = useState(0);
  const [blocked, setBlocked] = useState<string[]>([]);

  // the tree this person gets: hidden fields removed, view/edit set (what the server does for real)
  const seen = useMemo(() => {
    const pages: FormPage[] = [];
    for (const p of tree.pages) {
      const sections = p.sections
        .map((s) => ({
          ...s,
          fields: s.fields
            .map((f) => ({ f, e: effectiveLevel(role, stage, kind, f.type, { field: f.access, section: s.access, page: p.access }) }))
            .filter(({ e }) => e.level !== "hidden")
            .map(({ f, e }) => ({ ...f, level: e.level as "view" | "edit" })),
        }))
        .filter((s) => s.fields.length > 0);
      if (sections.length) pages.push({ ...p, sections });
    }
    return { pages, checks: tree.checks };
  }, [tree, role, stage, kind]);

  const pages = visiblePages(kind, seen, values);
  const at = Math.min(step, Math.max(0, pages.length - 1));
  const page = pages[at];
  function next() {
    if (page?.gate) {
      const gaps = pageGaps(kind, seen, page, values);
      if (gaps.length) return setBlocked(gaps.map((g) => g.label));
    }
    setBlocked([]);
    setStep(at + 1);
  }
  return (
    <Modal title="Preview" onClose={onClose} actions={<button onClick={onClose}>Close preview</button>} wide>
      <div className="bar">
        <div className="seg" role="group" aria-label="Preview as">
          {(["expert", "ops"] as const).map((r) => (
            <button
              key={r}
              aria-pressed={role === r}
              onClick={() => {
                setRole(r);
                setStep(0);
                setBlocked([]);
              }}
            >
              {r === "expert" ? "Expert" : "Ops"}
            </button>
          ))}
        </div>
        <label className="check" style={{ margin: 0 }}>
          Booking stage
          <select
            aria-label="Booking stage"
            value={stage}
            onChange={(e) => {
              setStage(e.target.value);
              setStep(0);
            }}
            style={{ width: "auto" }}
          >
            {STAGES.map((s) => (
              <option key={s} value={s}>
                {STAGE_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
        <span className="grow" />
        <div className="seg" role="group" aria-label="Device">
          <button aria-pressed={device === "phone"} onClick={() => setDevice("phone")}>
            <Smartphone size={14} aria-hidden /> Phone
          </button>
          <button aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}>
            <Monitor size={14} aria-hidden /> Desktop
          </button>
        </div>
      </div>
      <p className="muted small">
        Hidden fields, read-only fields, rules and page gates all work as they will for real. Photos and location are not sent anywhere.
      </p>
      <div className={`preview-frame ${device}`}>
        {!page ? (
          <p className="empty-state">Nothing to show for this role at this stage.</p>
        ) : (
          <>
            <p className="muted small">
              Page {at + 1} of {pages.length}
            </p>
            <h2 style={{ marginTop: 0 }}>
              {page.title}
              {page.gate && (
                <span className="chip" style={{ marginLeft: 8 }}>
                  <Lock size={11} aria-hidden /> must be finished
                </span>
              )}
            </h2>
            <FormRenderer
              kind={kind}
              tree={seen}
              values={values}
              pages={[page]}
              role={role}
              preview
              onChange={(k, v) => {
                setValues({ ...values, [k]: v });
                setBlocked([]);
              }}
            />
            {blocked.length > 0 && (
              <div className="card" role="alert">
                <strong>Finish this page first</strong>
                <ul>
                  {blocked.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="bar" style={{ marginTop: 10 }}>
              <button
                disabled={at === 0}
                onClick={() => {
                  setBlocked([]);
                  setStep(at - 1);
                }}
              >
                Back
              </button>
              <span className="grow" />
              {at < pages.length - 1 ? (
                <button className="primary" onClick={next}>
                  Next
                </button>
              ) : (
                <span className="muted small">End of the form</span>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
