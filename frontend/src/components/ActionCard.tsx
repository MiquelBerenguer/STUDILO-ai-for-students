// Feed action card (UX.md §4): Novi's proactive output. One-tap actions; inputs live inside the card.
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, ApiError, post } from "../api";
import { relTime, useJobRuns } from "../hooks";
import type { ActResult, CardAction, FeedCard, Upload } from "../types";
import { Icon, type IconName } from "./icons";
import { LiveRun } from "./LiveRun";
import { Markdown } from "./ui";

const KIND: Record<string, { label: string; icon: IconName; tone: string }> = {
  upload_prompt: { label: "Class ended", icon: "upload", tone: "bg-primary-soft text-primary" },
  missed_class: { label: "Missed class", icon: "calendar", tone: "bg-warm-soft text-[#d57d37]" },
  catch_up_ready: { label: "Catch-up ready", icon: "book", tone: "bg-blue-soft text-[#4a78cf]" },
  notes_filed: { label: "Done on my own", icon: "check", tone: "bg-success-soft text-success" },
  exam_pack_ready: { label: "Exam Pack", icon: "exam", tone: "bg-primary-soft text-primary" },
  exam_date_needed: { label: "Quick question", icon: "calendar", tone: "bg-blue-soft text-[#4a78cf]" },
  past_exams_wanted: { label: "Better practice exams", icon: "exam", tone: "bg-blue-soft text-[#4a78cf]" },
  syllabus_wanted: { label: "Quick question", icon: "text", tone: "bg-blue-soft text-[#4a78cf]" },
  approval: { label: "Needs your approval", icon: "alert", tone: "bg-warm-soft text-[#d57d37]" },
  answer: { label: "Answer", icon: "spark", tone: "bg-primary-soft text-primary" },
  job_failed: { label: "Something failed", icon: "alert", tone: "bg-red-50 text-red-600" },
  account_claim: { label: "Your account", icon: "settings", tone: "bg-canvas text-muted" },
  backfill_notes: { label: "Catch up", icon: "upload", tone: "bg-primary-soft text-primary" },
  deadline: { label: "Deadline", icon: "clock", tone: "bg-warm-soft text-[#d57d37]" },
  connect_calendar: { label: "Connect", icon: "link", tone: "bg-blue-soft text-[#4a78cf]" },
  info: { label: "Update", icon: "spark", tone: "bg-canvas text-muted" },
};

function cardTitle(card: FeedCard): string {
  const ends = card.data.ends_at as string | undefined;
  if (card.kind === "upload_prompt" && ends) {
    const course = card.title.replace(/^Your (.*) class ended.*$/, "$1");
    return `Your ${course} class ended ${relTime(ends)} — drop your notes here.`;
  }
  return card.title;
}

export function ActionCard({ card }: { card: FeedCard }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const meta = KIND[card.kind] ?? KIND.info;
  const long = ["answer", "catch_up_ready"].includes(card.kind);

  async function act(action: CardAction, value?: string) {
    setBusy(action.id);
    setError(null);
    try {
      const r = await post<ActResult>(`/cards/${card.id}/act`, { action: action.id, value });
      setMessage(r.message);
      if (r.job) setJobId(r.job.id);
      qc.invalidateQueries({ queryKey: ["feed"] });
      qc.invalidateQueries({ queryKey: ["exams"] });
      qc.invalidateQueries({ queryKey: ["courses"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const buttons = card.actions.filter((a) => a.type === "button" || a.type === "link");
  const inputs = card.actions.filter((a) => !["button", "link"].includes(a.type));

  return (
    <article data-testid="action-card" data-kind={card.kind}
      className="overflow-hidden rounded-2xl border border-[#dbd7ff] bg-white shadow-[var(--shadow-panel)]">
      <div className="flex gap-3 bg-gradient-to-r from-primary-soft/70 to-white px-4 py-3">
        <span className={`grid h-9 w-9 flex-none place-items-center rounded-xl ${meta.tone}`}>
          <Icon name={meta.icon} className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="eyebrow flex items-center gap-2 text-primary">
            {meta.label} <span className="font-semibold normal-case tracking-normal text-muted">· {relTime(card.created_at)}</span>
          </div>
          <h3 className="mt-0.5 text-[0.86rem] font-bold leading-snug">{cardTitle(card)}</h3>
        </div>
      </div>
      {card.body && (
        <div className="px-4 pb-1 pt-2.5 text-[0.76rem] leading-relaxed text-slate-600">
          {long ? <Markdown className="prose-sm">{card.body}</Markdown> : <p className="line-clamp-4 whitespace-pre-line">{card.body}</p>}
          {card.kind === "answer" && <Citations card={card} />}
        </div>
      )}
      {!message && inputs.map((a) => <InlineInput key={a.id} card={card} action={a} busy={busy === a.id}
        onSubmit={(v) => act(a, v)} onUploaded={(id) => { setJobId(id); setMessage("Got it — filing your notes…"); }} />)}
      {message && <p className="px-4 pt-2 text-[0.76rem] font-semibold text-success">{message}</p>}
      {error && <p className="px-4 pt-2 text-[0.76rem] text-red-600">{error}</p>}
      {jobId && <JobRuns jobId={jobId} />}
      {!message && buttons.length > 0 && (
        <div className="mt-2 grid border-t border-line" style={{ gridTemplateColumns: `repeat(${buttons.length}, 1fr)` }}>
          {buttons.map((a, i) => (
            <button key={a.id} disabled={!!busy}
              className={`px-3 py-2.5 text-[0.74rem] font-bold transition hover:bg-primary-soft ${i ? "border-l border-line" : ""} ${a.primary ? "text-primary" : "text-muted"}`}
              onClick={() => (a.type === "link" && a.href ? navigate(a.href) : act(a))}>
              {a.id === "undo" && <Icon name="undo" className="mr-1 inline h-3.5 w-3.5" />}
              {busy === a.id ? "…" : a.label}
            </button>
          ))}
        </div>
      )}
      {(message || buttons.length === 0) && <div className="h-3" />}
    </article>
  );
}

function Citations({ card }: { card: FeedCard }) {
  const cites = Object.entries((card.data.citations ?? {}) as Record<string, { topic_title: string; heading: string; course_id: string; topic_id: string }>);
  if (!cites.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {cites.map(([id, c]) => (
        <a key={id} href={`/subjects/${c.course_id}?topic=${c.topic_id}#${id}`} className="chip py-1 text-[0.66rem]">
          {c.topic_title} › {c.heading}
        </a>
      ))}
    </div>
  );
}

function JobRuns({ jobId }: { jobId: string }) {
  const { data: runs = [] } = useJobRuns(jobId);
  if (!runs.length) return null;
  return <div className="space-y-2 px-4 pt-2">{[...runs].reverse().map((r) => <LiveRun key={r.id} run={r} />)}</div>;
}

function InlineInput({ card, action, busy, onSubmit, onUploaded }: {
  card: FeedCard; action: CardAction; busy: boolean; onSubmit: (v: string) => void; onUploaded: (jobId: string) => void;
}) {
  const [value, setValue] = useState("");
  const wrap = (children: ReactNode) => <div className="px-4 pt-2.5">{children}</div>;
  if (action.type === "date") {
    return wrap(
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (value) onSubmit(value); }}>
        <input type="date" className="input" value={value} onChange={(e) => setValue(e.target.value)} required aria-label="Exam date" />
        <button className="btn-primary flex-none" disabled={busy || !value}>{busy ? "…" : action.label}</button>
      </form>,
    );
  }
  if (action.type === "text") {
    return wrap(
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (value.trim()) onSubmit(value); }}>
        <textarea className="input min-h-24" placeholder="1. Units and dimensions&#10;2. First law…" value={value}
          onChange={(e) => setValue(e.target.value)} />
        <button className="btn-primary" disabled={busy || !value.trim()}>{busy ? "…" : action.label}</button>
      </form>,
    );
  }
  if (action.type === "input") {
    return wrap(
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (value.trim()) onSubmit(value.trim()); }}>
        <input className="input" type={action.input_type ?? "text"} placeholder={action.placeholder} value={value}
          onChange={(e) => setValue(e.target.value)} required aria-label={action.label} />
        <button className="btn-primary flex-none" disabled={busy || !value.trim()}>{busy ? "…" : action.label}</button>
      </form>,
    );
  }
  if (action.type === "credentials") return wrap(<ClaimForm />);
  if (action.type === "upload") return wrap(<CardDropzone card={card} action={action} onUploaded={onUploaded} />);
  return null;
}

function CardDropzone({ card, action, onUploaded }: { card: FeedCard; action: CardAction; onUploaded: (jobId: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [courseId, setCourseId] = useState(action.params?.course_id ?? action.course_choices?.[0]?.id ?? "");
  const qc = useQueryClient();

  async function send(files: FileList | null) {
    if (!files?.length || !courseId) return;
    const fd = new FormData();
    fd.set("course_id", courseId);
    fd.set("kind", action.params?.kind ?? "notes");
    if (action.params?.class_session_id) fd.set("class_session_id", action.params.class_session_id);
    Array.from(files).forEach((f) => fd.append("files", f));
    try {
      const ups = await api<Upload[]>("/uploads", { method: "POST", body: fd });
      if (ups[0]?.job_id) onUploaded(ups[0].job_id);
      qc.invalidateQueries({ queryKey: ["feed"] });
      if (card.kind === "backfill_notes" || card.kind === "past_exams_wanted") setErr(null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <div>
      {action.course_choices && action.course_choices.length > 1 && (
        <select className="input mb-2" value={courseId} onChange={(e) => setCourseId(e.target.value)} aria-label="Course">
          {action.course_choices.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      )}
      <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); send(e.dataTransfer.files); }}
        className={`flex items-center justify-between gap-3 rounded-xl border-2 border-dashed px-3 py-3 text-[0.74rem] transition ${over ? "border-primary bg-primary-soft" : "border-[#dcd8ff] bg-canvas"}`}>
        <span className="text-muted">Drop PDFs, photos or text here</span>
        <span className="flex gap-1.5">
          <button type="button" className="btn-secondary px-2.5 py-1.5" onClick={() => camera.current?.click()}>
            <Icon name="camera" className="h-4 w-4" /> Photo
          </button>
          <button type="button" className="btn-primary px-2.5 py-1.5" onClick={() => input.current?.click()}>
            <Icon name="upload" className="h-4 w-4" /> {action.label}
          </button>
        </span>
        <input ref={input} type="file" multiple hidden accept=".pdf,.txt,.md,image/*" onChange={(e) => send(e.target.files)} />
        <input ref={camera} type="file" hidden accept="image/*" capture="environment" onChange={(e) => send(e.target.files)} />
      </div>
      {err && <p className="mt-1 text-[0.72rem] text-red-600">{err}</p>}
    </div>
  );
}

export function ClaimForm({ onDone }: { onDone?: () => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={async (e) => {
      e.preventDefault();
      setBusy(true);
      setErr(null);
      try {
        await post("/auth/claim", { email, password });
        qc.invalidateQueries({ queryKey: ["me"] });
        qc.invalidateQueries({ queryKey: ["feed"] });
        onDone?.();
      } catch (e2) {
        setErr(e2 instanceof Error ? e2.message : String(e2));
      } finally {
        setBusy(false);
      }
    }}>
      <input className="input" type="email" placeholder="you@uni.edu" value={email} onChange={(e) => setEmail(e.target.value)} required aria-label="Email" />
      <input className="input" type="password" placeholder="Password (8+ chars)" minLength={8} value={password}
        onChange={(e) => setPassword(e.target.value)} required aria-label="Password" />
      <button className="btn-primary" disabled={busy}>{busy ? "…" : "Save account"}</button>
      {err && <p className="text-[0.72rem] text-red-600 sm:col-span-3">{err}</p>}
    </form>
  );
}
