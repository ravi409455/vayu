import type { Inspection } from "../../../api/types";
import { AnswerValue, defectOf } from "../../../ui/AnswerSheet";
import { type MediaField, nearestChoice, type Trees } from "./parts";

export function AnswerNear({ insp, trees, f }: { insp: Inspection; trees: Trees; f: MediaField }) {
  const q = nearestChoice(trees, f);
  if (!q) return null;
  const v = (insp.answers[f.part] ?? {})[q.key];
  const sev = defectOf(q, v);
  return (
    <p className="small" style={{ margin: "6px 0 0" }}>
      {q.label}:{" "}
      <strong className={sev ? "bad-text" : ""}>
        <AnswerValue f={q} v={v} />
      </strong>
      {sev && (
        <>
          {" "}
          <span className="pill bad">{sev}</span>
        </>
      )}
    </p>
  );
}
