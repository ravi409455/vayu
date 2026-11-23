import { Link2, Unlink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../../api/client";
import { Field, InfoTip, useToast } from "../../../ui/kit";

/** Library actions for a field or a section: save it as a reusable item, or manage the link. */
export function LibraryBox({ kind, id, library, readOnly, onDone }: {
  kind: "field" | "section"; id: number; library: { item: number; revision: number | null; update_available: boolean } | null; readOnly: boolean; onDone: () => void;
}) {
  const { say, fail } = useToast();
  const [name, setName] = useState("");
  const path = `${kind}s/${id}`;
  if (readOnly && !library) return null;          // nothing to show on a field that is not linked
  const call = async (action: string, body: unknown, done: string) => {
    try { await api(`${path}/${action}`, { body }); say(done); onDone(); } catch (e) { fail(e); }
  };
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="bar" style={{ marginBottom: 6 }}><strong><Link2 size={14} aria-hidden /> Library</strong>
        <InfoTip>The library holds reusable {kind}s. A linked {kind} stays in sync with the library: when someone improves the library item you see “update available” and accept it. Copies are independent.</InfoTip></div>
      {library ? (
        <>
          <p className="small">Linked to a library item (revision {library.revision}). {library.update_available ? "A newer revision is available." : "Up to date."} Its settings come from the library and cannot be changed here.</p>
          <p className="small"><Link to={`/library/${library.item}`}>Edit in library</Link></p>
          {!readOnly && <div className="bar">
            {library.update_available && <button className="primary" onClick={() => call("accept-update", {}, "Updated from the library.")}>Accept update</button>}
            <button onClick={() => call("unlink", {}, "Unlinked: now a plain copy.")}><Unlink size={14} aria-hidden /> Unlink</button></div>}
        </>
      ) : (
        !readOnly && (
          <>
            <Field label="Save as a reusable item" help="Give it a name people will recognise."><input aria-label="Library item name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Tyre tread depth" /></Field>
            <button disabled={!name.trim()} onClick={() => call("save-to-library", { name: name.trim() }, "Saved to the library.")}>Save to library</button>
          </>
        )
      )}
    </div>
  );
}
