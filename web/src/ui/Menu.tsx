import { MoreHorizontal } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export type MenuItem = { label: string; onClick: () => void; danger?: boolean; hidden?: boolean };

const GAP = 6, MARGIN = 8;

/** Where a menu of this size goes next to its button: below and right-aligned, flipped above when
 *  there is no room below, kept inside the window. */
export function placeMenu(btn: { top: number; bottom: number; right: number }, menu: { width: number; height: number }, view: { width: number; height: number }) {
  const below = btn.bottom + GAP + menu.height <= view.height - MARGIN;
  const top = below ? btn.bottom + GAP : Math.max(MARGIN, btn.top - GAP - menu.height);
  const left = Math.min(Math.max(MARGIN, btn.right - menu.width), view.width - menu.width - MARGIN);
  return { top, left };
}

/** The "···" button: secondary and risky actions, each with a word, behind one click. The menu floats
 *  above the page (a portal), so a table's scroll box or a card's edge never cuts it off. */
export function MoreMenu({ label, items, children }: { label: string; items: MenuItem[]; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!open || !btn.current || !menu.current) return;
    const r = btn.current.getBoundingClientRect();
    setPos(placeMenu(r, menu.current.getBoundingClientRect(), { width: window.innerWidth, height: window.innerHeight }));
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { const t = e.target as Node; if (!btn.current?.contains(t) && !menu.current?.contains(t)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); btn.current?.focus(); } };
    const close = () => setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); window.removeEventListener("scroll", close, true); window.removeEventListener("resize", close); };
  }, [open]);
  useEffect(() => { if (!open) setPos(null); }, [open]);
  const shown = items.filter((i) => !i.hidden);
  if (shown.length === 0) return null;
  const plain = shown.filter((i) => !i.danger), risky = shown.filter((i) => i.danger);
  const pick = (i: MenuItem) => { setOpen(false); i.onClick(); };
  return (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- only stops the click reaching a clickable row behind
    <span className="menu-wrap" onClick={(e) => e.stopPropagation()}>
      <button ref={btn} className="icon-only" aria-label={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>{children ?? <MoreHorizontal size={16} aria-hidden />}</button>
      {open && createPortal(
        // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/interactive-supports-focus -- only stops the click reaching a clickable row behind; the items are buttons
        <div ref={menu} className="menu floating" role="menu" aria-label={label} onClick={(e) => e.stopPropagation()}
          style={{ top: pos?.top ?? -9999, left: pos?.left ?? -9999 }}>
          {plain.map((i) => <button key={i.label} role="menuitem" onClick={() => pick(i)}>{i.label}</button>)}
          {plain.length > 0 && risky.length > 0 && <div className="menu-sep" />}
          {risky.map((i) => <button key={i.label} role="menuitem" className="danger-item" onClick={() => pick(i)}>{i.label}</button>)}
        </div>, document.body)}
    </span>
  );
}
