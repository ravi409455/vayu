import { MoreHorizontal } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

export type MenuItem = { label: string; onClick: () => void; danger?: boolean; hidden?: boolean };

/** The "···" button: secondary and risky actions, each with a word, behind one click. */
export function MoreMenu({ label, items, children }: { label: string; items: MenuItem[]; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  const shown = items.filter((i) => !i.hidden);
  if (shown.length === 0) return null;
  const plain = shown.filter((i) => !i.danger), risky = shown.filter((i) => i.danger);
  return (
    <div className="menu-wrap" ref={wrap} onClick={(e) => e.stopPropagation()}>
      <button className="icon-only" aria-label={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>{children ?? <MoreHorizontal size={16} aria-hidden />}</button>
      {open && (
        <div className="menu" role="menu">
          {plain.map((i) => <button key={i.label} role="menuitem" onClick={() => { setOpen(false); i.onClick(); }}>{i.label}</button>)}
          {plain.length > 0 && risky.length > 0 && <div className="menu-sep" />}
          {risky.map((i) => <button key={i.label} role="menuitem" className="danger-item" onClick={() => { setOpen(false); i.onClick(); }}>{i.label}</button>)}
        </div>
      )}
    </div>
  );
}
