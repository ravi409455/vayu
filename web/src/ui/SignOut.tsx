import { useState, type ReactNode } from "react";
import { useAuth } from "../auth";
import { unsentWork } from "../lib/store";
import { Confirm } from "./kit";

/** Sign out, but first say what has not reached the office yet: signing out deletes it from this
 *  browser (F-242, R-06). With nothing unsent it signs out at once. */
export function useSignOut(): { start: () => void; dialog: ReactNode } {
  const { logout } = useAuth();
  const [work, setWork] = useState<{ drafts: number; files: number } | null>(null);
  const out = () => logout().catch(() => {}); // the browser forgets the person even if the call fails
  const start = () => void unsentWork().then((w) => (w.drafts || w.files ? setWork(w) : out()));
  const what = work
    ? [
        work.drafts && `${work.drafts} inspection draft${work.drafts === 1 ? "" : "s"}`,
        work.files && `${work.files} photo${work.files === 1 ? "" : "s"} or file${work.files === 1 ? "" : "s"}`,
      ]
        .filter(Boolean)
        .join(" and ")
    : "";
  const dialog = work && (
    <Confirm
      title="Sign out with work not sent?"
      danger
      confirmLabel="Sign out and delete it"
      cancelLabel="Stay signed in"
      onCancel={() => setWork(null)}
      onConfirm={out}
    >
      <p>
        This browser still holds {what} that the office does not have yet. Signing out deletes{" "}
        {work.drafts + work.files === 1 ? "it" : "them"} from this computer.
      </p>
      <p className="muted small">
        To keep {work.drafts + work.files === 1 ? "it" : "them"}: stay signed in, open the lead and let everything send, then sign out.
      </p>
    </Confirm>
  );
  return { start, dialog };
}
