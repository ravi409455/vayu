import { Bell, ChevronDown, LogOut, Search, Smartphone, UserRound } from "lucide-react";
import { useSignOut } from "./SignOut";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, type Page } from "../api/client";
import { STAGE_LABEL } from "../api/labels";
import type { Booking } from "../api/types";
import { useAuth } from "../auth";
import { Avatar } from "./Avatar";
import { useCrumbText } from "./crumb";
import { envName } from "./Logo";
import { useNeeds } from "../lib/problems";

/** Section of the app for each first path segment; detail pages name their parent list. */
const SECTION: Record<string, [string, string]> = {
  bookings: ["Bookings", "/bookings"], booking: ["Bookings", "/bookings"], today: ["Today", "/today"],
  problems: ["Needs you", "/problems"], dashboards: ["Dashboard", "/dashboards"], jobs: ["My leads", "/jobs"],
  forms: ["Forms", "/forms"], library: ["Library", "/library"], lists: ["Master lists", "/lists"],
  pdf: ["PDF templates", "/pdf"], users: ["Users", "/users"], roles: ["Roles & permissions", "/roles"],
  integrations: ["Integrations", "/integrations"], "api-keys": ["API keys", "/api-keys"], promote: ["Promote", "/promote"],
  audit: ["Audit log", "/audit"], profile: ["Your profile", "/profile"],
};

export function crumbsFor(path: string, last: string): { label: string; to?: string }[] {
  const [first = "", second] = path.split("/").filter(Boolean);
  const sec = SECTION[first];
  if (!sec) return [];
  if (!second && first !== "booking") return [{ label: sec[0] }];
  return [{ label: sec[0], to: sec[1] }, ...(last ? [{ label: last }] : [])];
}

function Crumbs() {
  const { pathname } = useLocation();
  const parts = crumbsFor(pathname, useCrumbText());
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      {parts.map((p, i) => (
        <span key={i} style={{ display: "contents" }}>
          {i > 0 && <span className="sep" aria-hidden="true">/</span>}
          {p.to ? <Link to={p.to}>{p.label}</Link> : <span className="here" aria-current="page">{p.label}</span>}
        </span>
      ))}
    </nav>
  );
}

/** Find a booking from anywhere: ID, customer, phone, chassis. Enter opens the full list. */
function GlobalSearch() {
  const nav = useNavigate();
  const box = useRef<HTMLInputElement>(null);
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  useEffect(() => { const t = setTimeout(() => setQ(term.trim()), 250); return () => clearTimeout(t); }, [term]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); box.current?.focus(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const res = useQuery({ queryKey: ["global-search", q], enabled: q.length >= 2, staleTime: 15_000,
    queryFn: () => api<Page<Booking>>("bookings", { query: { search: q } }) });
  const hits = (res.data?.results ?? []).slice(0, 6);
  const go = (to: string) => { setOpen(false); setTerm(""); box.current?.blur(); nav(to); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { setOpen(false); box.current?.blur(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(h + 1, hits.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
    else if (e.key === "Enter" && term.trim()) go(hits[hi] && open ? `/booking/${hits[hi].id}` : `/bookings?search=${encodeURIComponent(term.trim())}`);
  };
  return (
    <div className="gsearch">
      <label>
        <Search size={15} aria-hidden />
        <input ref={box} aria-label="Search bookings" placeholder="Search booking ID, customer, phone, chassis" value={term}
          onChange={(e) => { setTerm(e.target.value); setOpen(true); setHi(0); }} onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)} onKeyDown={onKey} />
        <kbd aria-hidden="true">⌘K</kbd>
      </label>
      {open && q.length >= 2 && (
        <div className="menu" role="listbox" aria-label="Matching bookings">
          {res.isLoading && <span className="muted small" style={{ padding: "8px 10px" }}>Searching…</span>}
          {!res.isLoading && hits.length === 0 && <span className="muted small" style={{ padding: "8px 10px" }}>No booking matches “{q}”.</span>}
          {hits.map((b, i) => (
            <a key={b.id} href={`/booking/${b.id}`} role="option" aria-selected={i === hi} className={i === hi ? "on" : ""}
              onMouseDown={(e) => { e.preventDefault(); go(`/booking/${b.id}`); }}>
              <strong>{b.booking_id}</strong>
              <span className="grow ellipsis muted">{String(b.answers.customer_name ?? "")}</span>
              <span className="chip">{STAGE_LABEL[b.stage] ?? b.stage}</span>
            </a>
          ))}
          {hits.length > 0 && <a href={`/bookings?search=${encodeURIComponent(q)}`} onMouseDown={(e) => { e.preventDefault(); go(`/bookings?search=${encodeURIComponent(q)}`); }} className="muted small">See all results</a>}
        </div>
      )}
    </div>
  );
}

function AccountMenu() {
  const { me } = useAuth();
  const signOut = useSignOut();
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
  if (!me) return null;
  const name = me.name || me.username;
  return (
    <div className="menu-wrap" ref={wrap}>
      <button className="acct-btn who-name" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Avatar who={me} size={28} decorative /><span>{name.split(" ")[0]}</span><span className="sr-only"> account menu</span><ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head"><strong>{name}</strong><div className="muted small" style={{ textTransform: "capitalize" }}>{me.role}</div></div>
          <Link role="menuitem" to="/profile" onClick={() => setOpen(false)}><UserRound size={16} aria-hidden /> Your profile</Link>
          <Link role="menuitem" to="/app" onClick={() => setOpen(false)}><Smartphone size={16} aria-hidden /> Get the Android app</Link>
          <button role="menuitem" onClick={() => { setOpen(false); signOut.start(); }}><LogOut size={16} aria-hidden /> Sign out</button>
        </div>
      )}
      {signOut.dialog}
    </div>
  );
}

/** The bell: how many things need a person, and the list itself one click away. */
function NeedsBell() {
  const { needs, total, error, refetch } = useNeeds();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="menu-wrap" ref={wrap}>
      <button className="icon-btn bell" aria-label={total ? `Needs you: ${total}` : "Needs you: nothing"} aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen(!open)}>
        <Bell size={18} aria-hidden />{total > 0 && <span className="bell-dot">{total}</span>}
      </button>
      {open && (
        <div className="menu needs-pop" role="dialog" aria-label="Needs you">
          <div className="needs-head"><strong className="grow">Needs you</strong><span className="muted small">{total || "Nothing"}</span></div>
          {error ? <p className="error small" role="alert" style={{ padding: "6px 10px" }}>Could not check what needs you. <button className="link" onClick={() => void refetch()}>Try again</button></p>
            : needs.length === 0 && <p className="muted small" style={{ padding: "6px 10px" }}>All clear. Nothing needs a person right now.</p>}
          {needs.slice(0, 7).map((n) => (
            <Link key={n.key} to={n.to} className="need-item" onClick={() => setOpen(false)}>
              <span className={`dot ${n.tone}`} aria-hidden="true" />
              <span className="grow" style={{ minWidth: 0 }}><span className="need-title">{n.title}</span><span className="need-meta">{n.meta}</span></span>
              <span className="need-act">{n.action}</span>
            </Link>))}
          <Link to="/problems" className="needs-all" onClick={() => setOpen(false)}>{total > 7 ? `See all ${total}` : "Open the list"}</Link>
        </div>)}
    </div>
  );
}

export function TopBar() {
  const { me, can } = useAuth();
  const env = envName();
  return (
    <header className="topbar">
      <Crumbs />
      {me && me.role !== "expert" && can("bookings.view") && <GlobalSearch />}
      <div className="right">
        {env && <span className="env" title="Which server this is">{env}</span>}
        {me && me.role !== "expert" && can("bookings.view") && <NeedsBell />}
        <AccountMenu />
      </div>
    </header>
  );
}
