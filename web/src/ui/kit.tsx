import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { explain } from "../api/client";

export function Modal({ title, children, onClose, actions }: { title: string; children: ReactNode; onClose: () => void; actions?: ReactNode }) {
  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        {children}
        <div className="actions">{actions ?? <button onClick={onClose}>Close</button>}</div>
      </div>
    </div>
  );
}

export function Confirm({ title, children, confirmLabel = "Confirm", danger, onConfirm, onCancel }: {
  title: string; children: ReactNode; confirmLabel?: string; danger?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <Modal title={title} onClose={onCancel}
      actions={<><button onClick={onCancel}>Cancel</button>
        <button className={danger ? "danger" : "primary"} onClick={onConfirm}>{confirmLabel}</button></>}>
      {children}
    </Modal>
  );
}

type ToastCtx = { say: (msg: string, bad?: boolean) => void; fail: (e: unknown) => void };
const Toasts = createContext<ToastCtx>({ say: () => {}, fail: () => {} });
export const useToast = () => useContext(Toasts);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<{ msg: string; bad: boolean } | null>(null);
  const say = useCallback((msg: string, bad = false) => {
    setT({ msg, bad });
    setTimeout(() => setT(null), 4000);
  }, []);
  const fail = useCallback((e: unknown) => say(explain(e), true), [say]);
  return (
    <Toasts.Provider value={{ say, fail }}>
      {children}
      {t && <div className={`toast${t.bad ? " bad" : ""}`} role="status">{t.msg}</div>}
    </Toasts.Provider>
  );
}

/** A labelled input. `bare` uses a plain box instead of a <label> wrapper: needed when the
 *  content has its own buttons (a label would swallow their accessible names). */
export function Field({ label, help, error, children, bare }: { label: string; help?: string; error?: string; children: ReactNode; bare?: boolean }) {
  const body = (
    <>
      <span>{label}</span>
      {children}
      {help && <span className="help">{help}</span>}
      {error && <span className="error" role="alert">{error}</span>}
    </>
  );
  return bare ? <div className="field">{body}</div> : <label className="field">{body}</label>;
}

export function Pill({ children, tone }: { children: ReactNode; tone?: "ok" | "warn" | "bad" | "info" }) {
  return <span className={`pill${tone ? " " + tone : ""}`}>{children}</span>;
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} className={value === t.id ? "on" : ""} onClick={() => onChange(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function when(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="muted pad">{children}</p>;
}

/** Asks for one short text (a page or section name) in a proper dialog. */
export function NameDialog({ title, label, onOk, onCancel }: { title: string; label: string; onOk: (v: string) => void; onCancel: () => void }) {
  const [v, setV] = useState("");
  return (
    <Modal title={title} onClose={onCancel}
      actions={<><button onClick={onCancel}>Cancel</button><button className="primary" disabled={!v.trim()} onClick={() => onOk(v.trim())}>Add</button></>}>
      <Field label={label}><input autoFocus value={v} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === "Enter" && v.trim() && onOk(v.trim())} /></Field>
    </Modal>
  );
}
