import { Info } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

/** The little "i": hover (or focus, or tap) for a plain-words explanation of what something is for.
 *  ``before``: text shown in front of the "i" that opens it on hover too (a whole history line). */
export function InfoTip({ children, label = "More info", before }: { children: ReactNode; label?: string; before?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    const hide = () => setOpen(false); // it is fixed to the screen: scrolling would leave it behind
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    window.addEventListener("scroll", hide, true);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
      window.removeEventListener("scroll", hide, true);
    };
  }, [open]);
  // fixed to the screen (a scrolling side panel would cut it off), kept inside the window
  const at = () => {
    const r = box.current?.getBoundingClientRect();
    if (!r) return undefined;
    const width = Math.min(280, window.innerWidth - 16);
    return {
      position: "fixed" as const,
      top: r.bottom + 6,
      left: Math.max(8, Math.min(r.left - 8, window.innerWidth - width - 8)),
      maxWidth: width,
    };
  };
  return (
    <span className="tip" ref={box} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      {before}
      <button
        type="button"
        className="tip-btn"
        aria-label={label}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen(true);
        }}
      >
        <Info size={14} aria-hidden />
      </button>
      {open && (
        <span role="tooltip" id={id} className="tip-pop" style={at()}>
          {children}
        </span>
      )}
    </span>
  );
}
