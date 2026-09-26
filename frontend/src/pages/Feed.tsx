// Home: the Novi feed (UX.md §3). What I did · what I need from you · what I'll do next.
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { post } from "../api";
import { ActionCard } from "../components/ActionCard";
import { CommandPanel } from "../components/CommandBar";
import { Icon } from "../components/icons";
import { LiveRun } from "../components/LiveRun";
import { ErrorBox, Skeleton } from "../components/ui";
import { clock, useFeature, useFeed } from "../hooks";
import type { Feed as FeedT, WeekItem } from "../types";

const WEEK_STATE: Record<WeekItem["state"], { label: string; cls: string }> = {
  upcoming: { label: "Later", cls: "bg-canvas text-muted" },
  in_progress: { label: "Now", cls: "bg-primary-soft text-primary" },
  ended: { label: "Waiting for notes", cls: "bg-warm-soft text-[#b86a2c]" },
  notes_in: { label: "Notes in", cls: "bg-success-soft text-success" },
  missed: { label: "Missed", cls: "bg-red-50 text-red-600" },
};

export default function Feed() {
  const { data: feed, error, isLoading, refetch } = useFeed();
  const [params, setParams] = useSearchParams();
  const welcome = params.get("welcome") === "1";

  useEffect(() => {
    const seen = () => { void post("/feed/seen").catch(() => undefined); };
    const onVis = () => document.visibilityState === "hidden" && seen();
    document.addEventListener("visibilitychange", onVis);
    return () => { document.removeEventListener("visibilitychange", onVis); seen(); };
  }, []);

  if (error) {
    return (
      <div className="card">
        <ErrorBox error={error} />
        <button className="btn-secondary mt-3" onClick={() => refetch()}>Retry</button>
      </div>
    );
  }
  if (isLoading || !feed) return <div className="card"><Skeleton lines={6} /></div>;

  return (
    <div data-testid="novi-feed" className="mx-auto max-w-[86rem] space-y-4">
      <Hero feed={feed} />
      {welcome && (
        <div className="flex items-center gap-3 rounded-2xl border border-success/30 bg-success-soft px-4 py-3 text-[0.8rem]">
          <Icon name="check" className="h-5 w-5 text-success" />
          <span className="flex-1">
            <b>You're set.</b>{" "}
            {feed.next[0]?.kind === "class_end"
              ? `I'll ping you when your next class ends (${clock(feed.next[0].at)}).`
              : "I'll ping you when your next class ends."}
          </span>
          <button className="btn-ghost px-2 py-1" onClick={() => setParams({})} aria-label="Close"><Icon name="x" className="h-4 w-4" /></button>
        </div>
      )}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(19rem,0.65fr)]">
        <div className="space-y-4">
          <Section title="Needs you" subtitle="Things only you can do — one tap each" count={feed.cards.length}>
            {feed.cards.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-line p-5 text-center text-[0.8rem] text-muted">
                All caught up. {feed.next[0] ? `Next: ${feed.next[0].text} (${clock(feed.next[0].at)}).` : ""}
              </p>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">{feed.cards.map((c) => <ActionCard key={c.id} card={c} />)}</div>
            )}
          </Section>
          {feed.live.length > 0 && (
            <Section title="Working now" subtitle="Live — every step is a real agent step" live={feed.live.length}>
              <div className="space-y-2">{feed.live.map((r) => <LiveRun key={r.id} run={r} defaultOpen />)}</div>
            </Section>
          )}
          <Section title="Since you were away" subtitle="What I did on my own. Expand any run to see its steps.">
            {feed.since.length === 0
              ? <p className="text-[0.78rem] text-muted">Nothing yet — I start working when your first class ends or you drop notes.</p>
              : <div className="space-y-2">{feed.since.map((r) => <LiveRun key={r.id} run={r} defaultOpen={false} />)}</div>}
          </Section>
        </div>
        <aside className="space-y-4">
          <Section title="Next up" subtitle="What I'll do next, and when">
            {feed.next.length === 0 ? <p className="text-[0.78rem] text-muted">Nothing planned yet.</p> : (
              <ol className="space-y-2.5">
                {feed.next.map((n, i) => (
                  <li key={i} className="flex gap-3">
                    <span className={`grid h-8 w-8 flex-none place-items-center rounded-lg ${n.kind === "exam_pack" ? "bg-primary-soft text-primary" : n.kind === "check" ? "bg-warm-soft text-[#d57d37]" : "bg-blue-soft text-[#4a78cf]"}`}>
                      <Icon name={n.kind === "exam_pack" ? "exam" : n.kind === "check" ? "clock" : n.kind === "calendar" ? "link" : "calendar"} className="h-4 w-4" />
                    </span>
                    <span>
                      <span className="eyebrow block">{clock(n.at)}</span>
                      <span className="text-[0.76rem] font-semibold">{n.text}</span>
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Section>
          <Section title="Your day" subtitle="Today's classes">
            {feed.week.length === 0 ? <p className="text-[0.78rem] text-muted">No classes today.</p> : (
              <ol>
                {feed.week.map((w, i) => (
                  <li key={i} className="grid grid-cols-[3rem_1rem_minmax(0,1fr)_auto] items-center gap-2 py-2">
                    <span className="text-[0.68rem] font-semibold text-muted">{w.start}</span>
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: w.color }} />
                    <span className="truncate text-[0.78rem] font-semibold">{w.course}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[0.6rem] font-bold ${WEEK_STATE[w.state].cls}`}>{WEEK_STATE[w.state].label}</span>
                  </li>
                ))}
              </ol>
            )}
          </Section>
          <Section title="How I work" subtitle="What I do on my own, and what I ask first">
            <ul className="space-y-2">
              {feed.policy.map((p) => (
                <li key={p.action} className="flex items-start gap-2 text-[0.72rem]">
                  <span className={`mt-0.5 rounded-full px-1.5 py-0.5 text-[0.56rem] font-bold uppercase ${p.risk === "low" ? "bg-success-soft text-success" : "bg-warm-soft text-[#b86a2c]"}`}>{p.risk === "low" ? "auto" : "asks"}</span>
                  <span><b className="font-semibold">{p.action}</b><span className="text-muted"> — {p.mode}</span></span>
                </li>
              ))}
            </ul>
          </Section>
          <FlaggedStubs />
        </aside>
      </div>
    </div>
  );
}

function Hero({ feed }: { feed: FeedT }) {
  const working = feed.counts.running > 0;
  return (
    <section className="novi-hero px-5 py-5 sm:px-7 sm:py-6">
      <div className="relative z-10 flex items-center gap-5">
        <div className={`novi-orbit hidden sm:grid ${working ? "is-working" : ""}`}>
          <span />
          <div className="novi-core"><Icon name="spark" solid className="h-6 w-6" /></div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[0.6rem] font-bold uppercase tracking-[0.12em] text-white/70">
            <span className="pulse-dot" />
            Watching {feed.counts.classes} class{feed.counts.classes === 1 ? "" : "es"} · {feed.counts.needs_you} need{feed.counts.needs_you === 1 ? "s" : ""} you · {feed.counts.running} running
          </div>
          <h1 className="mt-2 text-[1.55rem] font-bold leading-tight tracking-[-0.04em] sm:text-[1.8rem]">
            {working ? "I'm on it." : feed.counts.needs_you ? `Hi ${feed.user_name}, a few things need you.` : `Hi ${feed.user_name}, I've got this.`}
          </h1>
          <p className="mt-1 max-w-2xl text-[0.78rem] leading-relaxed text-white/70">{feed.status_line}</p>
        </div>
      </div>
      <div className="relative z-10 mt-4">
        <CommandPanel dark suggestions={feed.suggestions} />
      </div>
    </section>
  );
}

function Section({ title, subtitle, count, live, children }: {
  title: string; subtitle?: string; count?: number; live?: number; children: React.ReactNode;
}) {
  return (
    <section className="card p-5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h2 className="section-title">{title}{count ? <span className="ml-2 rounded-full bg-primary-soft px-2 py-0.5 text-[0.66rem] text-primary">{count}</span> : null}</h2>
          {subtitle && <p className="mt-0.5 text-[0.7rem] text-muted">{subtitle}</p>}
        </div>
        {live ? <span className="flex items-center gap-1.5 text-[0.62rem] font-bold text-success"><span className="live-dot is-live" />{live} running</span> : null}
      </div>
      {children}
    </section>
  );
}

// Reference-design elements without a backend yet: hidden unless their flag is on (UX.md §10).
function FlaggedStubs() {
  const insights = useFeature("study_habits_insights");
  if (!insights) return null;
  return (
    <section className="card border-dashed p-5 text-[0.76rem] text-muted">
      <span className="eyebrow">Stub · study_habits_insights</span>
      <p className="mt-1">Study-habit insights are not implemented yet.</p>
    </section>
  );
}
