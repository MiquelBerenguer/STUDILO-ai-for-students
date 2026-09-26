// Timetable capture + editable week preview (UX.md §8). Shared by onboarding and Schedule → re-import.
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api, ApiError, get } from "../api";
import type { ExtractedSlot, Extraction, LiveRunT } from "../types";
import { Icon } from "./icons";
import { LiveRun } from "./LiveRun";
import { WEEKDAYS } from "./ui";

const LOW = 0.8;

/** Step 1: one screen, every input the student might already have. */
export function TimetableCapture({ beforeExtract, onExtracted }: {
  beforeExtract?: () => Promise<void>; onExtracted: (x: Extraction) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<"drop" | "text" | "link">("drop");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);

  async function run(form: FormData) {
    setBusy(true);
    setError(null);
    try {
      await beforeExtract?.();
      setStartedAt(Date.now()); // only once a session exists, so the live-run poll is authorised
      const x = await api<Extraction>("/onboarding/extract", { method: "POST", body: form });
      if (!x.slots.length) setError(x.warnings[0] ?? "I couldn't find any classes there.");
      else onExtracted(x);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const sendFile = (files: FileList | null) => {
    if (!files?.[0]) return;
    const fd = new FormData();
    fd.set("file", files[0]);
    void run(fd);
  };

  return (
    <div>
      <div className="mb-3 flex gap-1 rounded-xl bg-canvas p-1 text-[0.74rem] font-bold">
        {([["drop", "Screenshot, photo or PDF", "camera"], ["link", "Calendar link / .ics", "link"], ["text", "Paste text", "text"]] as const).map(([m, label, icon]) => (
          <button key={m} onClick={() => setMode(m)} className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-2 transition ${mode === m ? "bg-white text-primary shadow-sm" : "text-muted hover:text-ink"}`}>
            <Icon name={icon} className="h-4 w-4" /><span className="hidden sm:inline">{label}</span>
          </button>
        ))}
      </div>
      {mode === "drop" && (
        <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); sendFile(e.dataTransfer.files); }}
          onClick={() => !busy && fileRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-[var(--radius-card)] border-2 border-dashed px-6 py-12 text-center transition ${over ? "border-primary bg-primary-soft" : "border-[#d8d3ff] bg-canvas hover:bg-primary-soft/50"}`}>
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-primary text-white shadow-lg"><Icon name="upload" className="h-6 w-6" /></span>
          <p className="mt-4 text-[1rem] font-bold">Drop your timetable here</p>
          <p className="mt-1 text-[0.76rem] text-muted">A screenshot from the campus site, a photo of the printout, the PDF, or an .ics file.</p>
          <input ref={fileRef} data-testid="timetable-file" type="file" hidden accept="image/*,.pdf,.ics,text/calendar"
            onChange={(e) => sendFile(e.target.files)} />
        </div>
      )}
      {mode === "link" && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); const fd = new FormData(); fd.set("url", url); void run(fd); }}>
          <input className="input" placeholder="webcal://… or https://…/calendar.ics" value={url} onChange={(e) => setUrl(e.target.value)} required aria-label="Calendar link" />
          <p className="text-[0.7rem] text-muted">Most virtual campuses (Moodle: Calendar → Export) give you a link like this. Exam dates in it are imported too.</p>
          <button className="btn-primary w-full" disabled={busy}>Read my calendar</button>
        </form>
      )}
      {mode === "text" && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); const fd = new FormData(); fd.set("text", text); void run(fd); }}>
          <textarea className="input min-h-36 font-mono text-[0.76rem]" value={text} onChange={(e) => setText(e.target.value)} required aria-label="Timetable text"
            placeholder={"Monday 9:00-11:00 Thermodynamics, Aula A2-101\nTuesday 11-13 Fluid Dynamics\n…"} />
          <button className="btn-primary w-full" disabled={busy}>Read it</button>
        </form>
      )}
      {busy && startedAt && <ExtractionRun since={startedAt} />}
      {error && <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-[0.76rem] text-red-700">{error}</p>}
    </div>
  );
}

/** The live trace of the Timetable agent while the request is in flight (real steps, polled). */
function ExtractionRun({ since }: { since: number }) {
  const { data: runs = [] } = useQuery({
    queryKey: ["runs", "onboarding", since],
    queryFn: () => get<LiveRunT[]>("/runs/live").catch(() => [] as LiveRunT[]),
    refetchInterval: 700,
  });
  const run = runs.find((r) => r.agent === "onboarding" && new Date(r.created_at).getTime() >= since - 2000);
  return (
    <div className="mt-3">
      {run ? <LiveRun run={run} defaultOpen /> : <p className="text-[0.76rem] text-muted">Sending…</p>}
    </div>
  );
}

/** Step 2: "Here's your week — looks right?" Everything pre-filled; low-confidence fields highlighted. */
export function WeekPreview({ extraction, slots, onChange }: {
  extraction: Extraction; slots: ExtractedSlot[]; onChange: (s: ExtractedSlot[]) => void;
}) {
  const days = [0, 1, 2, 3, 4, ...[5, 6].filter((d) => slots.some((s) => s.weekday === d))];
  const low = slots.reduce((n, s) => n + Object.values(s.confidence).filter((v) => v < LOW).length, 0);
  const update = (i: number, patch: Partial<ExtractedSlot>, field?: keyof ExtractedSlot["confidence"]) =>
    onChange(slots.map((s, j) => (j === i ? { ...s, ...patch, confidence: field ? { ...s.confidence, [field]: 1 } : s.confidence } : s)));
  const remove = (i: number) => onChange(slots.filter((_, j) => j !== i));
  const add = (weekday: number) => onChange([...slots, { subject: "", weekday, start: "09:00", end: "10:00", room: "",
    professor: "", confidence: { subject: 0, time: 1, room: 1, professor: 1 } }]);
  const how = { grid: "read the grid myself — no AI needed", ics: "read your calendar — no AI needed",
    text: "read your text — no AI needed", vision: "used the AI reader for this one", llm_text: "used the AI reader",
    none: "" }[extraction.method];

  return (
    <div data-testid="schedule-preview">
      <p className="mb-3 text-[0.78rem] text-muted">
        Found <b className="text-ink">{slots.length} classes</b> ({how}).{" "}
        {low > 0 ? <span className="font-semibold text-[#b86a2c]">{low} field{low > 1 ? "s" : ""} to double-check (amber).</span> : "Everything looks confident."}
        {extraction.exams.length > 0 && <> Also found <b className="text-ink">{extraction.exams.length} exam date{extraction.exams.length > 1 ? "s" : ""}</b>.</>}
      </p>
      {extraction.warnings.map((w) => <p key={w} className="mb-2 rounded-lg bg-warm-soft px-3 py-1.5 text-[0.72rem] text-[#8a5a2b]">{w}</p>)}
      <div className="grid gap-2 overflow-x-auto" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(9.5rem, 1fr))` }}>
        {days.map((d) => (
          <div key={d} className="rounded-2xl bg-canvas p-2">
            <div className="eyebrow mb-2 px-1">{WEEKDAYS[d]}</div>
            <div className="space-y-2">
              {slots.map((s, i) => s.weekday === d && (
                <div key={i} className="rounded-xl border border-line bg-white p-2 shadow-sm">
                  <div className="flex items-start gap-1">
                    <Field value={s.subject} low={s.confidence.subject < LOW} bold placeholder="Subject"
                      onChange={(v) => update(i, { subject: v }, "subject")} />
                    <button className="text-muted hover:text-red-600" onClick={() => remove(i)} aria-label="Remove class"><Icon name="x" className="h-3.5 w-3.5" /></button>
                  </div>
                  <div className="mt-1 grid grid-cols-[1fr_auto_1fr] items-center gap-1">
                    <Field value={s.start} low={s.confidence.time < LOW} type="time" onChange={(v) => update(i, { start: v }, "time")} />
                    <span className="text-muted">–</span>
                    <Field value={s.end} low={s.confidence.time < LOW} type="time" onChange={(v) => update(i, { end: v }, "time")} />
                  </div>
                  <Field value={s.room} low={s.confidence.room < LOW} placeholder="Room" small onChange={(v) => update(i, { room: v }, "room")} />
                  {(s.professor || s.confidence.professor < LOW) && (
                    <Field value={s.professor} low={s.confidence.professor < LOW} placeholder="Professor" small onChange={(v) => update(i, { professor: v }, "professor")} />
                  )}
                </div>
              ))}
              <button className="w-full rounded-lg py-1 text-[0.68rem] font-semibold text-muted hover:bg-white hover:text-primary" onClick={() => add(d)}>+ Add a class</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Field({ value, onChange, low, bold, small, type = "text", placeholder }: {
  value: string; onChange: (v: string) => void; low?: boolean; bold?: boolean; small?: boolean; type?: string; placeholder?: string;
}) {
  return (
    <span className="relative min-w-0 flex-1">
      <input type={type} value={value} step={type === "time" ? 300 : undefined} placeholder={placeholder} onChange={(e) => onChange(e.target.value)}
        title={low ? "I'm not sure about this one — please check" : undefined}
        className={`w-full min-w-0 rounded-md border px-1.5 py-0.5 outline-none focus:border-primary ${small ? "mt-1 text-[0.66rem] text-muted" : "text-[0.74rem]"} ${bold ? "font-bold" : ""} ${type === "time" ? "time-compact tabular-nums" : ""} ${low ? "border-warm bg-warm-soft" : "border-transparent hover:border-line"}`} />
      {low && <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-warm" />}
    </span>
  );
}
