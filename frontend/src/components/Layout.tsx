import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { get, post } from "../api";
import type { Course, Me, Notification } from "../types";
import { fmtTime } from "./ui";
import { BRAND } from "../brand";

const NAV = [
  { to: "/", label: "Today", end: true },
  { to: "/upload", label: "Upload" },
  { to: "/exams", label: "Exams" },
  { to: "/activity", label: "Activity" },
  { to: "/settings", label: "Settings" },
];

const linkCls = ({ isActive }: { isActive: boolean }) =>
  `block rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"}`;

export default function Layout({ me }: { me: Me }) {
  const { data: courses = [] } = useQuery({ queryKey: ["courses"], queryFn: () => get<Course[]>("/courses") });
  const qc = useQueryClient();
  const navigate = useNavigate();

  async function logout() {
    await post("/auth/logout");
    qc.clear();
    qc.setQueryData(["me"], null);
    navigate("/login");
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="no-print border-b border-slate-200 bg-white md:sticky md:top-0 md:h-screen md:w-60 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between px-4 py-4">
          <span className="text-xl font-bold text-indigo-700">{BRAND.name}</span>
          <div className="md:hidden"><Inbox /></div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:block md:space-y-1">
          {NAV.slice(0, 2).map((n) => <NavLink key={n.to} to={n.to} end={n.end} className={linkCls}>{n.label}</NavLink>)}
          <div className="hidden px-3 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-slate-400 md:block">Subjects</div>
          {courses.map((c) => (
            <NavLink key={c.id} to={`/subjects/${c.id}`} className={linkCls}>
              <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: c.color }} />
              {c.name}
            </NavLink>
          ))}
          <div className="hidden pt-3 md:block" />
          {NAV.slice(2).map((n) => <NavLink key={n.to} to={n.to} className={linkCls}>{n.label}</NavLink>)}
        </nav>
      </aside>
      <div className="flex-1">
        <header className="no-print sticky top-0 z-10 hidden items-center justify-end gap-3 border-b border-slate-200 bg-white/80 px-6 py-3 backdrop-blur md:flex">
          <Inbox />
          <span className="text-sm text-slate-500">{me.display_name || me.email}</span>
          <button className="btn-ghost" onClick={logout}>Log out</button>
        </header>
        <main className="mx-auto max-w-6xl p-4 md:p-6">
          <Outlet />
        </main>
        <div className="no-print p-4 text-center md:hidden">
          <button className="btn-ghost" onClick={logout}>Log out</button>
        </div>
      </div>
    </div>
  );
}

function Inbox() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const seen = useRef<Set<string> | null>(null);
  const { data: items = [] } = useQuery({
    queryKey: ["inbox"],
    queryFn: () => get<Notification[]>("/inbox?limit=30"),
    refetchInterval: 15_000,
  });
  const unread = items.filter((n) => !n.read_at);
  const [permission, setPermission] = useState(typeof Notification !== "undefined" ? Notification.permission : "denied");

  // Browser notifications for new unread items (after the first load).
  useEffect(() => {
    if (seen.current === null) {
      seen.current = new Set(items.map((n) => n.id));
      return;
    }
    for (const n of unread) {
      if (!seen.current.has(n.id) && permission === "granted") {
        const notif = new window.Notification(n.title, { body: n.body.slice(0, 180), tag: n.id });
        notif.onclick = () => { window.focus(); if (n.link) navigate(n.link); };
      }
    }
    seen.current = new Set(items.map((n) => n.id));
  }, [items, unread, permission, navigate]);

  async function openItem(n: Notification) {
    if (!n.read_at) await post(`/inbox/${n.id}/read`);
    qc.invalidateQueries({ queryKey: ["inbox"] });
    setOpen(false);
    if (n.link) navigate(n.link);
  }

  return (
    <div className="relative">
      <button className="btn-ghost relative" onClick={() => setOpen(!open)} aria-label="Inbox">
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2c0 .5-.2 1-.6 1.4L4 17h5m6 0a3 3 0 1 1-6 0" />
        </svg>
        {unread.length > 0 && (
          <span className="absolute -right-0.5 -top-0.5 rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">
            {unread.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-sm font-semibold">Inbox</span>
            <button className="text-xs text-indigo-600" onClick={async () => {
              await post("/inbox/read-all");
              qc.invalidateQueries({ queryKey: ["inbox"] });
            }}>Mark all read</button>
          </div>
          {permission === "default" && (
            <button className="w-full bg-indigo-50 px-3 py-2 text-left text-xs text-indigo-700"
              onClick={async () => setPermission(await Notification.requestPermission())}>
              Enable browser notifications for class-end prompts and exam packs
            </button>
          )}
          <ul className="max-h-96 overflow-y-auto">
            {items.length === 0 && <li className="p-4 text-center text-sm text-slate-500">Nothing yet.</li>}
            {items.map((n) => (
              <li key={n.id}>
                <button onClick={() => openItem(n)} className={`w-full px-3 py-2 text-left hover:bg-slate-50 ${n.read_at ? "opacity-60" : ""}`}>
                  <div className="text-sm font-medium">{!n.read_at && <span className="mr-1 text-indigo-600">●</span>}{n.title}</div>
                  <div className="line-clamp-2 text-xs text-slate-500">{n.body}</div>
                  <div className="text-[10px] text-slate-400">{fmtTime(n.created_at)}</div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
