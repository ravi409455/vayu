import { Info } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

/** The little "i": click (or focus) for a plain-words explanation of what something is for. */
export function InfoTip({ children, label = "More info" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return (
    <span className="tip" ref={box}>
      <button type="button" className="tip-btn" aria-label={label} aria-expanded={open} aria-describedby={open ? id : undefined}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(!open); }}>
        <Info size={14} aria-hidden />
      </button>
      {open && <span role="tooltip" id={id} className="tip-pop">{children}</span>}
    </span>
  );
}
