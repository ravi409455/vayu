import { useEffect, useState } from "react";

/** One or two capital letters for a person: first and last word of the name (or the username). */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const first = words[0]![0]!;
  const last = words.length > 1 ? words[words.length - 1]![0]! : "";
  return (first + last).toUpperCase();
}

const COLOURS = ["#a62830", "#2b6cb0", "#2f855a", "#975a16", "#6b46c1", "#c05621", "#2c7a7b", "#97266d"];
/** The same person always gets the same colour. */
export function colourFor(seed: string): string {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COLOURS[h % COLOURS.length]!;
}

export type Who = { id?: number; name?: string; username?: string; avatar_url?: string | null };

/** The person's picture, or their initials on a colour when they have none (or it will not load). */
export function Avatar({ who, size = 32, decorative }: { who: Who; size?: number; decorative?: boolean }) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [who.avatar_url]);
  const label = who.name || who.username || "";
  const style = { width: size, height: size, fontSize: Math.round(size * 0.4) };
  if (who.avatar_url && !broken) {
    return <img className="avatar" style={style} src={who.avatar_url} alt={decorative ? "" : label ? `Picture of ${label}` : "Picture"} onError={() => setBroken(true)} />;
  }
  return <span className="avatar initials" style={{ ...style, background: colourFor(label || String(who.id ?? "")) }} {...(decorative ? { "aria-hidden": true } : { role: "img", "aria-label": label || "Person" })}>{initials(label)}</span>;
}
