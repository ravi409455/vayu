import { Modal, when } from "./kit";

export type Stale = { by: string; at: string; keys: string[]; rowVersion: number };

/** Someone else saved first. Say who and when, and offer to carry on with only the fields this
 *  person changed (everything else keeps the other person's value). */
export function StaleDialog({ info, mine, onRetry, onReload }: { info: Stale; mine: string[]; onRetry: () => void; onReload: () => void }) {
  const clash = mine.filter((k) => info.keys.includes(k));
  return (
    <Modal
      title={`${info.by} changed this${info.at ? " " + when(info.at) : ""}`}
      onClose={onReload}
      actions={
        <>
          <button onClick={onReload}>Discard mine and reload</button>
          <button className="primary" onClick={onRetry}>
            Save only my {mine.length} change{mine.length === 1 ? "" : "s"}
          </button>
        </>
      }
    >
      <p>
        They changed: <strong>{info.keys.join(", ") || "something"}</strong>.
      </p>
      <p>
        You changed: <strong>{mine.join(", ")}</strong>.
      </p>
      {clash.length > 0 && (
        <p className="error" role="alert">
          Both of you changed {clash.join(", ")}: saving will replace their value with yours.
        </p>
      )}
      <p className="muted small">Fields only they changed stay as they set them.</p>
    </Modal>
  );
}
