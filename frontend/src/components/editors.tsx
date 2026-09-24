import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { del, get, post, put } from "../api";
import type { Assignment, Course, Exam, Me, Slot } from "../types";
import { daysUntil, ErrorBox, fmtDate, WEEKDAYS } from "./ui";

const COLORS = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6"];

export function useCourses() {
  return useQuery({ queryKey: ["courses"], queryFn: () => get<Course[]>("/courses") });
}

function useInvalidate(...keys: string[]) {
  const qc = useQueryClient();
  return () => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}

export function CoursesEditor() {
  const { data: courses = [] } = useCourses();
  const [name, setName] = useState("");
  const [syllabus, setSyllabus] = useState("");
  const invalidate = useInvalidate("courses");
  const add = useMutation({
    mutationFn: () => post<Course>("/courses", { name, syllabus, color: COLORS[courses.length % COLORS.length] }),
    onSuccess: () => { setName(""); setSyllabus(""); invalidate(); },
  });
  const remove = useMutation({ mutationFn: (id: string) => del(`/courses/${id}`), onSuccess: invalidate });

  return (
    <div className="space-y-4">
      <form className="space-y-2" onSubmit={(e: FormEvent) => { e.preventDefault(); if (name.trim()) add.mutate(); }}>
        <div className="flex gap-2">
          <input className="input" placeholder="Subject name, e.g. Thermodynamics" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn-primary shrink-0" disabled={!name.trim() || add.isPending}>Add subject</button>
        </div>
        <textarea className="input h-20" placeholder="Optional: syllabus / list of units (helps track the class pace)"
          value={syllabus} onChange={(e) => setSyllabus(e.target.value)} />
        <ErrorBox error={add.error} />
      </form>
      {courses.length === 0 ? (
        <p className="text-sm text-slate-500">Add the subjects you are taking this semester.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {courses.map((c) => (
            <li key={c.id} className="flex items-center justify-between px-3 py-2">
              <span className="flex items-center gap-2 text-sm font-medium">
                <span className="h-3 w-3 rounded-full" style={{ background: c.color }} />{c.name}
                {c.syllabus && <span className="text-xs font-normal text-slate-400">syllabus added</span>}
              </span>
              <button className="btn-danger" onClick={() => confirm(`Delete ${c.name} and all its data?`) && remove.mutate(c.id)}>Remove</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ScheduleEditor() {
  const { data: courses = [] } = useCourses();
  const { data: slots = [] } = useQuery({ queryKey: ["slots"], queryFn: () => get<Slot[]>("/slots") });
  const [courseId, setCourseId] = useState("");
  const [weekday, setWeekday] = useState(0);
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("11:00");
  const invalidate = useInvalidate("slots");
  const add = useMutation({
    mutationFn: () => post(`/courses/${courseId || courses[0]?.id}/slots`, { weekday, start_time: start, end_time: end }),
    onSuccess: invalidate,
  });
  const remove = useMutation({ mutationFn: (id: string) => del(`/slots/${id}`), onSuccess: invalidate });
  const byId = Object.fromEntries(courses.map((c) => [c.id, c]));

  return (
    <div className="space-y-4">
      <form className="grid grid-cols-2 gap-2 md:grid-cols-5" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <select className="input col-span-2 md:col-span-1" value={courseId || courses[0]?.id || ""} onChange={(e) => setCourseId(e.target.value)}>
          {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input" value={weekday} onChange={(e) => setWeekday(Number(e.target.value))}>
          {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
        </select>
        <input className="input" type="time" value={start} onChange={(e) => setStart(e.target.value)} />
        <input className="input" type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
        <button className="btn-primary" disabled={!courses.length || add.isPending}>Add class</button>
      </form>
      <ErrorBox error={add.error} />
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-7">
        {WEEKDAYS.map((d, i) => (
          <div key={d} className="min-h-24 rounded-lg border bg-slate-50 p-2">
            <div className="mb-1 text-xs font-semibold text-slate-500">{d}</div>
            {slots.filter((s) => s.weekday === i).map((s) => (
              <div key={s.id} className="group mb-1 rounded-md px-2 py-1 text-xs text-white" style={{ background: byId[s.course_id]?.color ?? "#64748b" }}>
                <div className="font-medium">{byId[s.course_id]?.name}</div>
                <div className="flex justify-between">{s.start_time}–{s.end_time}
                  <button className="opacity-0 group-hover:opacity-100" onClick={() => remove.mutate(s.id)} aria-label="Remove">✕</button>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function ProfileEditor({ me, onSaved }: { me: Me; onSaved?: () => void }) {
  const [start, setStart] = useState(me.semester_start ?? "");
  const [end, setEnd] = useState(me.semester_end ?? "");
  const [tz, setTz] = useState(me.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [hours, setHours] = useState(me.missed_after_hours);
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => put<Me>("/me/profile", { semester_start: start || null, semester_end: end || null, timezone: tz, missed_after_hours: hours }),
    onSuccess: (m) => { qc.setQueryData(["me"], m); onSaved?.(); },
  });
  return (
    <form className="grid gap-3 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div><label className="label">Semester start</label><input className="input" type="date" required value={start} onChange={(e) => setStart(e.target.value)} /></div>
      <div><label className="label">Semester end</label><input className="input" type="date" required value={end} onChange={(e) => setEnd(e.target.value)} /></div>
      <div><label className="label">Timezone</label><input className="input" value={tz} onChange={(e) => setTz(e.target.value)} /></div>
      <div><label className="label">Remind me about missing notes after (hours)</label>
        <input className="input" type="number" min={1} max={168} value={hours} onChange={(e) => setHours(Number(e.target.value))} /></div>
      <div className="md:col-span-2 flex items-center gap-3">
        <button className="btn-primary" disabled={save.isPending}>Save</button>
        {save.isSuccess && <span className="text-sm text-emerald-600">Saved</span>}
        <ErrorBox error={save.error} />
      </div>
    </form>
  );
}

export function ExamsEditor() {
  const { data: courses = [] } = useCourses();
  const { data: exams = [] } = useQuery({ queryKey: ["exams"], queryFn: () => get<Exam[]>("/exams") });
  const { data: assignments = [] } = useQuery({ queryKey: ["assignments"], queryFn: () => get<Assignment[]>("/assignments") });
  const [courseId, setCourseId] = useState("");
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [scope, setScope] = useState("");
  const [aTitle, setATitle] = useState("");
  const [aDate, setADate] = useState("");
  const invalidate = useInvalidate("exams", "assignments");
  const cid = courseId || courses[0]?.id || "";
  const add = useMutation({
    mutationFn: () => post("/exams", { course_id: cid, title, exam_date: date, scope_note: scope }),
    onSuccess: () => { setTitle(""); setDate(""); setScope(""); invalidate(); },
  });
  const addA = useMutation({
    mutationFn: () => post("/assignments", { course_id: cid, title: aTitle, due_date: aDate }),
    onSuccess: () => { setATitle(""); setADate(""); invalidate(); },
  });
  const removeExam = useMutation({ mutationFn: (id: string) => del(`/exams/${id}`), onSuccess: invalidate });
  const removeA = useMutation({ mutationFn: (id: string) => del(`/assignments/${id}`), onSuccess: invalidate });
  const byId = Object.fromEntries(courses.map((c) => [c.id, c]));

  return (
    <div className="space-y-5">
      <form className="grid gap-2 md:grid-cols-4" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <select className="input" value={cid} onChange={(e) => setCourseId(e.target.value)}>
          {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input className="input" placeholder="Exam title, e.g. Midterm" required value={title} onChange={(e) => setTitle(e.target.value)} />
        <input className="input" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        <button className="btn-primary" disabled={!cid || add.isPending}>Add exam</button>
        <input className="input md:col-span-4" placeholder="Optional scope, e.g. Units 1–4 (what enters the exam)" value={scope} onChange={(e) => setScope(e.target.value)} />
      </form>
      <ErrorBox error={add.error} />
      <ul className="divide-y rounded-lg border">
        {exams.length === 0 && <li className="p-3 text-sm text-slate-500">No exams yet.</li>}
        {exams.map((x) => (
          <li key={x.id} className="flex items-center justify-between px-3 py-2 text-sm">
            <span><b>{x.title}</b> · {byId[x.course_id]?.name} · {fmtDate(x.exam_date, { dateStyle: "medium" })}
              <span className="ml-2 text-slate-400">in {daysUntil(x.exam_date)} days</span></span>
            <button className="btn-danger" onClick={() => removeExam.mutate(x.id)}>Remove</button>
          </li>
        ))}
      </ul>
      <details className="rounded-lg border p-3" open={assignments.length > 0}>
        <summary className="cursor-pointer text-sm font-medium">Assignments (optional)</summary>
        <form className="mt-3 grid gap-2 md:grid-cols-4" onSubmit={(e) => { e.preventDefault(); addA.mutate(); }}>
          <select className="input" value={cid} onChange={(e) => setCourseId(e.target.value)}>
            {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <input className="input" placeholder="Assignment" required value={aTitle} onChange={(e) => setATitle(e.target.value)} />
          <input className="input" type="date" required value={aDate} onChange={(e) => setADate(e.target.value)} />
          <button className="btn-secondary" disabled={!cid}>Add</button>
        </form>
        <ul className="mt-2 text-sm">
          {assignments.map((a) => (
            <li key={a.id} className="flex justify-between py-1">
              <span>{a.title} · {byId[a.course_id]?.name} · due {fmtDate(a.due_date)}</span>
              <button className="btn-danger" onClick={() => removeA.mutate(a.id)}>Remove</button>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
