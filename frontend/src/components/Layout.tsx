// App shell from the reference design: sidebar (bottom nav on phones), topbar, ⌘K command palette.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { post } from "../api";
import { BRAND } from "../brand";
import { useFeed } from "../hooks";
import type { Me } from "../types";
import { ClaimForm } from "./ActionCard";
import { CommandPaletteProvider, usePalette } from "./CommandBar";
import { BrandMark, Icon, type IconName } from "./icons";

const NAV: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/", label: BRAND.name, icon: "spark", end: true },
  { to: "/schedule", label: "Schedule", icon: "calendar" },
  { to: "/courses", label: "Courses", icon: "book" },
  { to: "/exams", label: "Exam prep", icon: "exam" },
  { to: "/activity", label: "Activity", icon: "chart" },
];

const TITLES: [RegExp, string][] = [
  [/^\/schedule/, "Schedule"], [/^\/courses|^\/subjects/, "Courses"], [/^\/exams|^\/packs/, "Exam prep"],
  [/^\/activity/, "Activity"], [/^\/settings/, "Settings"], [/^\/upload/, "Upload"],
];

export default function Layout({ me }: { me: Me }) {
  return (
    <CommandPaletteProvider>
      <Shell me={me} />
    </CommandPaletteProvider>
  );
}

function Shell({ me }: { me: Me }) {
  const location = useLocation();
  const palette = usePalette();
  const { data: feed } = useFeed();
  const navigate = useNavigate();
  useBrowserNotifications();
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 19 ? "Good afternoon" : "Good evening";
  const title = TITLES.find(([re]) => re.test(location.pathname))?.[1]
    ?? `${greeting}${me.display_name ? `, ${me.display_name}` : ""}`;
  const openCards = feed?.counts.needs_you ?? 0;

  return (
    <div className="min-h-screen">
      <aside className="no-print fixed inset-x-0 bottom-0 z-30 flex h-16 border-t border-line bg-white px-2 sm:inset-y-0 sm:left-0 sm:right-auto sm:h-auto sm:w-[4.8rem] sm:flex-col sm:border-r sm:border-t-0 sm:px-2.5 sm:py-8 lg:w-[15.5rem] lg:px-5">
        <div className="hidden items-center gap-3 px-2 pb-10 sm:flex sm:justify-center lg:justify-start">
          <BrandMark />
          <span className="hidden text-[1.3rem] font-bold tracking-[-0.04em] lg:inline">{BRAND.name}</span>
        </div>
        <nav className="flex flex-1 items-stretch justify-around gap-1 sm:flex-none sm:flex-col sm:justify-start" aria-label="Main navigation">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={({ isActive }) => `flex flex-1 flex-col items-center justify-center gap-0.5 rounded-[var(--radius-control)] px-2 py-1.5 text-[0.62rem] font-semibold transition sm:flex-none sm:flex-row sm:justify-center sm:py-3 lg:justify-start lg:gap-3.5 lg:px-3.5 lg:text-[0.88rem] ${isActive ? "bg-primary-soft text-primary-dark" : "text-muted hover:bg-canvas hover:text-ink"}`}>
              <Icon name={n.icon} solid={n.icon === "spark"} className="h-5 w-5" />
              <span className="sm:hidden lg:inline">{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="hidden sm:mt-auto sm:block">
          <NavLink to="/settings" className={({ isActive }) => `flex items-center justify-center gap-3.5 rounded-[var(--radius-control)] px-3.5 py-3 text-[0.88rem] font-semibold lg:justify-start ${isActive ? "bg-primary-soft text-primary-dark" : "text-muted hover:bg-canvas hover:text-ink"}`}>
            <Icon name="settings" className="h-5 w-5" /><span className="hidden lg:inline">Settings</span>
          </NavLink>
          <Profile me={me} />
        </div>
      </aside>

      <div className="sm:ml-[4.8rem] lg:ml-[15.5rem]">
        <header className="no-print sticky top-0 z-20 flex h-[5.5rem] items-center justify-between gap-3 border-b border-line bg-white/85 px-4 backdrop-blur-lg sm:h-[6.8rem] sm:px-10">
          <div className="min-w-0">
            <div className="eyebrow hidden sm:block">
              {new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
            </div>
            <div className="mt-1 truncate text-[1.25rem] font-bold tracking-[-0.035em] sm:text-[1.65rem]">{title}</div>
          </div>
          <div className="flex items-center gap-3">
            <button className="relative grid h-11 w-11 place-items-center rounded-full border border-line bg-white transition hover:border-primary hover:text-primary"
              onClick={() => navigate("/")} aria-label={`${openCards} things need you`}>
              <Icon name="bell" />
              {openCards > 0 && <span className="absolute right-1.5 top-1.5 grid h-4 min-w-4 place-items-center rounded-full border-2 border-white bg-primary px-1 text-[0.55rem] font-bold text-white">{openCards}</span>}
            </button>
            <button className="btn-primary px-4 py-3" onClick={() => palette.open()}>
              <Icon name="spark" solid className="h-4 w-4" /><span className="hidden sm:inline">Ask {BRAND.name}</span>
              <kbd className="hidden rounded bg-white/20 px-1 text-[0.6rem] md:inline">⌘K</kbd>
            </button>
          </div>
        </header>
        <main className="px-3 pb-24 pt-4 sm:px-10 sm:pb-12 sm:pt-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function Profile({ me }: { me: Me }) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const name = me.display_name || (me.is_guest ? "Guest" : me.email ?? "");
  const initials = name.split(/\s|@/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("") || "N";

  async function logout() {
    if (me.is_guest && !window.confirm("You haven't saved this account yet. Logging out loses everything. Log out anyway?")) return;
    await post("/auth/logout");
    qc.clear();
    qc.setQueryData(["me"], null);
    navigate("/");
  }

  return (
    <div className="relative mt-4 border-t border-line pt-4">
      <button className="flex w-full items-center justify-center gap-2.5 rounded-xl p-1 text-left hover:bg-canvas lg:justify-start" onClick={() => setOpen(!open)}>
        <span className="grid h-9 w-9 flex-none place-items-center rounded-full bg-primary-soft text-[0.72rem] font-bold text-primary-dark">{initials}</span>
        <span className="hidden min-w-0 flex-1 lg:block">
          <span className="block truncate text-[0.78rem] font-bold">{name}</span>
          <span className="block truncate text-[0.65rem] text-muted">{me.is_guest ? "Not saved yet" : me.email}</span>
        </span>
      </button>
      {open && (
        <div className="absolute bottom-14 left-0 z-40 w-72 rounded-2xl border border-line bg-white p-3 shadow-xl">
          {me.is_guest && (
            <div className="mb-3">
              <p className="mb-2 text-[0.72rem] text-muted">Save your account to keep your notes and use other devices.</p>
              <ClaimForm onDone={() => setOpen(false)} />
            </div>
          )}
          {typeof Notification !== "undefined" && Notification.permission === "default" && (
            <button className="btn-ghost w-full justify-start" onClick={() => { void Notification.requestPermission(); setOpen(false); }}>
              <Icon name="bell" className="h-4 w-4" /> Notify me when a class ends
            </button>
          )}
          <button className="btn-ghost w-full justify-start" onClick={logout}>Log out</button>
        </div>
      )}
    </div>
  );
}

/** New open cards → browser notifications while a tab is open (the feed stays the reliable channel). */
function useBrowserNotifications() {
  const { data: feed } = useFeed();
  const navigate = useNavigate();
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!feed) return;
    const ids = new Set(feed.cards.map((c) => c.id));
    if (seen.current && typeof Notification !== "undefined" && Notification.permission === "granted") {
      for (const c of feed.cards) {
        if (!seen.current.has(c.id)) {
          const n = new window.Notification(c.title, { body: c.body.slice(0, 160), tag: c.id });
          n.onclick = () => { window.focus(); navigate("/"); };
        }
      }
    }
    seen.current = ids;
  }, [feed, navigate]);
}
