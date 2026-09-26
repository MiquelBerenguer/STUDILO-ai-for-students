// Schedule (secondary view): the weekly grid Novi follows. Re-import reuses the onboarding capture.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { del, get, post } from "../api";
import { Icon } from "../components/icons";
import { TimetableCapture, WeekPreview } from "../components/Timetable";
import { Empty, WEEKDAYS } from "../components/ui";
import type { Course, ExtractedSlot, Extraction, Slot } from "../types";

export default function Schedule() {
  const { data: slots = [] } = useQuery({ queryKey: ["slots"], queryFn: () => get<Slot[]>("/slots") });
  const { data: courses = [] } = useQuery({ queryKey: ["courses"], queryFn: () => get<Course[]>("/courses") });
  const [importing, setImporting] = useState(false);
  const qc = useQueryClient();
  const byId = Object.fromEntries(courses.map((c) => [c.id, c]));
  const days = [0, 1, 2, 3, 4, ...[5, 6].filter((d) => slots.some((s) => s.weekday === d))];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[0.8rem] text-muted">I follow these classes and ask for notes when each one ends.</p>
        <button className="btn-secondary" onClick={() => setImporting(!importing)}>
          <Icon name="upload" className="h-4 w-4" /> {importing ? "Close" : "Import timetable"}
        </button>
      </div>
      {importing && <Import onDone={() => { setImporting(false); qc.invalidateQueries(); }} />}
      {slots.length === 0 ? <Empty title="No classes yet">Import your timetable and I'll take it from there.</Empty> : (
        <div className="card overflow-x-auto p-4">
          <div className="grid min-w-[40rem] gap-3" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
            {days.map((d) => (
              <div key={d}>
                <div className="eyebrow mb-2">{WEEKDAYS[d]}</div>
                <div className="space-y-2">
                  {slots.filter((s) => s.weekday === d).sort((a, b) => a.start_time.localeCompare(b.start_time)).map((s) => (
                    <div key={s.id} className="group rounded-xl p-2.5" style={{ background: `${byId[s.course_id]?.color ?? "#6558e8"}1f` }}>
                      <div className="flex items-start justify-between gap-1">
                        <span className="text-[0.76rem] font-bold">{byId[s.course_id]?.name}</span>
                        <button className="opacity-0 transition group-hover:opacity-100" aria-label="Delete class"
                          onClick={async () => { if (window.confirm("Remove this class from your week?")) { await del(`/slots/${s.id}`); qc.invalidateQueries({ queryKey: ["slots"] }); } }}>
                          <Icon name="x" className="h-3.5 w-3.5 text-muted" />
                        </button>
                      </div>
                      <div className="text-[0.68rem] text-muted">{s.start_time}–{s.end_time}{s.location ? ` · ${s.location}` : ""}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Import({ onDone }: { onDone: () => void }) {
  const [x, setX] = useState<Extraction | null>(null);
  const [slots, setSlots] = useState<ExtractedSlot[]>([]);
  const [busy, setBusy] = useState(false);
  return (
    <div className="card">
      {!x ? <TimetableCapture onExtracted={(e) => { setX(e); setSlots(e.slots); }} /> : (
        <>
          <WeekPreview extraction={x} slots={slots} onChange={setSlots} />
          <div className="mt-3 flex justify-end gap-2">
            <button className="btn-ghost" onClick={() => setX(null)}>Try another</button>
            <button className="btn-primary" disabled={busy} onClick={async () => {
              setBusy(true);
              await post("/onboarding/confirm", { slots: slots.filter((s) => s.subject.trim()), exams: x.exams });
              onDone();
            }}>Add to my week</button>
          </div>
        </>
      )}
    </div>
  );
}
