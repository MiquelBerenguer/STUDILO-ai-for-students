// Command bar (UX.md §6): natural language → the right agent / job / proposal. Inline in the hero, ⌘K anywhere.
// Results are cards and live runs, never canned chat replies.
import { useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { post } from "../api";
import { useFeed, useJob, useJobRuns } from "../hooks";
import type { CommandResult } from "../types";
import { ActionCard } from "./ActionCard";
import { Icon } from "./icons";
import { LiveRun } from "./LiveRun";

const PaletteCtx = createContext<{ open: (text?: string) => void }>({ open: () => undefined });
export const usePalette = () => useContext(PaletteCtx);

export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ open: boolean; text: string }>({ open: false, text: "" });
  const open = useCallback((text = "") => setState({ open: true, text }), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setState((s) => ({ open: !s.open, text: "" }));
      } else if (e.key === "Escape") {
        setState((s) => ({ ...s, open: false }));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <PaletteCtx.Provider value={{ open }}>
      {children}
      {state.open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-ink/30 p-4 pt-[12vh] backdrop-blur-sm"
          onMouseDown={(e) => e.target === e.currentTarget && setState((s) => ({ ...s, open: false }))}>
          <div data-testid="command-palette" className="w-full max-w-2xl rounded-[var(--radius-card)] bg-white p-3 shadow-2xl">
            <CommandPanel autoFocus initialText={state.text} onNavigate={() => setState((s) => ({ ...s, open: false }))} />
          </div>
        </div>
      )}
    </PaletteCtx.Provider>
  );
}

export function CommandPanel({ autoFocus, initialText = "", dark, suggestions = [], onNavigate }: {
  autoFocus?: boolean; initialText?: string; dark?: boolean; suggestions?: string[]; onNavigate?: () => void;
}) {
  const [text, setText] = useState(initialText);
  const [asked, setAsked] = useState<string | null>(null);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();

  useEffect(() => { if (autoFocus) inputRef.current?.focus(); }, [autoFocus]);

  async function send(q: string) {
    const clean = q.trim();
    if (clean.length < 2) return;
    setBusy(true);
    setError(null);
    setAsked(clean);
    try {
      const r = await post<CommandResult>("/command", { text: clean });
      setResult(r);
      setText("");
      qc.invalidateQueries({ queryKey: ["feed"] });
      if (r.outcome === "navigate" && r.route) {
        navigate(r.route);
        onNavigate?.();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form onSubmit={(e) => { e.preventDefault(); send(text); }}
        className={`flex items-center gap-2 rounded-2xl border p-1.5 pl-3 transition focus-within:ring-4 ${dark
          ? "border-white/20 bg-white/10 focus-within:border-white/50 focus-within:ring-white/10"
          : "border-line bg-canvas focus-within:border-primary focus-within:ring-primary-soft"}`}>
        <Icon name="spark" solid className={`h-4 w-4 ${dark ? "text-[#bdf6de]" : "text-primary"}`} />
        <input ref={inputRef} data-testid="command-input" value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Tell Novi what to do… e.g. make me a 1h exam on entropy"
          className={`min-w-0 flex-1 bg-transparent py-1.5 text-[0.84rem] outline-none ${dark ? "text-white placeholder:text-white/55" : "placeholder:text-muted"}`}
          aria-label="Command" />
        <kbd className={`hidden rounded-md px-1.5 py-0.5 text-[0.62rem] font-semibold sm:block ${dark ? "bg-white/10 text-white/60" : "bg-white text-muted"}`}>⌘K</kbd>
        <button className={`grid h-9 w-9 place-items-center rounded-xl transition ${dark ? "bg-white text-primary-dark hover:bg-white/90" : "bg-primary text-white hover:bg-primary-dark"}`}
          disabled={busy} aria-label="Send">
          <Icon name="send" className="h-4 w-4" />
        </button>
      </form>
      {!asked && suggestions.length > 0 && (
        <div className="mt-2.5 flex gap-2 overflow-x-auto pb-1">
          {suggestions.map((s) => (
            <button key={s} onClick={() => send(s)}
              className={dark ? "flex-none rounded-full border border-white/20 px-3 py-1.5 text-[0.68rem] font-semibold text-white/85 hover:bg-white/10" : "chip"}>
              {s}
            </button>
          ))}
        </div>
      )}
      {asked && (
        <div className={`mt-3 rounded-2xl p-3 ${dark ? "bg-white text-ink" : "bg-canvas"}`}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="truncate rounded-full bg-primary px-3 py-1 text-[0.7rem] font-semibold text-white">{asked}</span>
            <button className="btn-ghost px-2 py-1" onClick={() => { setAsked(null); setResult(null); }} aria-label="Clear">
              <Icon name="x" className="h-3.5 w-3.5" />
            </button>
          </div>
          {busy && <p className="text-[0.76rem] text-muted">Routing your request…</p>}
          {error && <p className="text-[0.76rem] text-red-600">{error}</p>}
          {result && <Outcome result={result} asked={asked} onResend={send} />}
        </div>
      )}
    </div>
  );
}

function Outcome({ result, asked, onResend }: { result: CommandResult; asked: string; onResend: (q: string) => void }) {
  const [date, setDate] = useState("");
  return (
    <div className="space-y-2">
      <p className="text-[0.78rem] font-semibold">
        {result.message}
        <span className="ml-2 rounded-full bg-white px-2 py-0.5 text-[0.6rem] font-semibold text-muted">
          {result.intent.replace(/_/g, " ")} · {result.method === "llm" ? "understood by AI" : "understood without AI"}
        </span>
      </p>
      {result.outcome === "needs" && result.needs !== "date" && (
        <div className="flex flex-wrap gap-1.5">
          {result.choices.map((c) => <button key={c.id} className="chip" onClick={() => onResend(`${asked} ${c.label}`)}>{c.label}</button>)}
        </div>
      )}
      {result.outcome === "needs" && result.needs === "date" && (
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (date) onResend(`${asked} ${date}`); }}>
          <input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} aria-label="New date" />
          <button className="btn-primary">Propose</button>
        </form>
      )}
      {result.outcome === "job" && result.job_id && <JobOutcome jobId={result.job_id} />}
      {result.outcome === "proposal" && result.card_id && <CardById id={result.card_id} />}
      {result.outcome === "info" && result.route && (
        <a href={result.route} className="chip">Open {result.route.replace("/", "")}</a>
      )}
    </div>
  );
}

function JobOutcome({ jobId }: { jobId: string }) {
  const { data: runs = [] } = useJobRuns(jobId);
  const { data: job } = useJob(jobId);
  const cardId = job?.result?.card_id as string | undefined;
  return (
    <div className="space-y-2">
      {[...runs].reverse().map((r) => <LiveRun key={r.id} run={r} />)}
      {runs.length === 0 && job?.state === "queued" && <p className="text-[0.74rem] text-muted">Queued — starting in a moment…</p>}
      {job?.state === "failed" && <JobError error={job.error} />}
      {cardId && <CardById id={cardId} />}
    </div>
  );
}

function JobError({ error }: { error: string }) {
  const [open, setOpen] = useState(false);
  const aiDown = error.startsWith("LLMUnavailable");
  return (
    <div className="text-[0.74rem] text-red-600">
      {aiDown ? "The AI models are busy or unavailable right now. Try again in a minute." : error.split("\n")[0].slice(0, 200)}
      {aiDown && (
        <button className="ml-2 font-semibold underline" onClick={() => setOpen(!open)}>{open ? "Hide details" : "Details"}</button>
      )}
      {open && <pre className="mt-1 whitespace-pre-wrap break-words text-[0.64rem] text-muted">{error}</pre>}
    </div>
  );
}

function CardById({ id }: { id: string }) {
  const { data: feed } = useFeed();
  const card = feed?.cards.find((c) => c.id === id);
  if (!card) return <p className="text-[0.74rem] text-muted">Done — it's in your feed.</p>;
  return <ActionCard card={card} />;
}
