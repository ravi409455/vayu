import type { User } from "../api/types";
import { Avatar } from "./Avatar";

/** The assigned expert in a list: their picture (or initials) and name, or a dash when nobody is assigned. */
export function ExpertCell({ id, experts }: { id: number | null; experts: User[] }) {
  if (!id) return <span className="muted">—</span>;
  const u = experts.find((e) => e.id === id);
  return (
    <span className="who-avatar">
      <Avatar who={u ?? { id }} size={22} />
      {u ? u.name || u.username : `#${id}`}
    </span>
  );
}
