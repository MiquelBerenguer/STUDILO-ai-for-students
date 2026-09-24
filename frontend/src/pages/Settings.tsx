import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { get, post, put } from "../api";
import { useMe } from "../App";
import { CoursesEditor, ProfileEditor, ScheduleEditor, useCourses } from "../components/editors";
import { Badge, Card, ErrorBox, fmtDate, Skeleton } from "../components/ui";
import type { ClassSession, Exam, Job, ProviderStatus, Slot, TaskMapping } from "../types";

export default function Settings() {
  const { data: me } = useMe();
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Settings</h1>
      <Providers />
      <Models />
      <Card title="Profile & semester">{me ? <ProfileEditor me={me} /> : <Skeleton />}</Card>
      <Card title="Subjects"><CoursesEditor /></Card>
      <Card title="Weekly schedule"><ScheduleEditor /></Card>
      <Simulate />
    </div>
  );
}

function Providers() {
  const { data = [] } = useQuery({ queryKey: ["providers"], queryFn: () => get<ProviderStatus[]>("/settings/providers") });
  const [results, setResults] = useState<Record<string, { ok: boolean; message: string } | "pending">>({});
  async function test(name: string) {
    setResults((r) => ({ ...r, [name]: "pending" }));
    const res = await post<{ ok: boolean; message: string }>(`/settings/providers/${name}/test`);
    setResults((r) => ({ ...r, [name]: res }));
  }
  return (
    <Card title="Providers" action={<span className="text-xs text-slate-500">Keys live in <code>.env</code> — edit it and restart. They are never shown here.</span>}>
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-slate-400"><tr><th>Provider</th><th>Key</th><th>Used by</th><th /></tr></thead>
        <tbody>
          {data.map((p) => {
            const r = results[p.name];
            return (
              <tr key={p.name} className="border-t align-top">
                <td className="py-2 font-medium">{p.name}<div className="text-xs font-normal text-slate-400">{p.base_url}</div></td>
                <td className="py-2">
                  {p.key_env === null ? <Badge tone="gray">no key needed</Badge> : p.configured
                    ? <span><Badge tone="green">configured</Badge> <code className="text-xs">{p.masked_key}</code></span>
                    : <span><Badge tone={p.used_by.length ? "red" : "gray"}>not set</Badge> <code className="text-xs">{p.key_env}</code></span>}
                </td>
                <td className="py-2 text-xs">{p.used_by.join(", ") || "–"}</td>
                <td className="py-2 text-right">
                  <button className="btn-secondary px-2 py-1 text-xs" disabled={r === "pending"} onClick={() => test(p.name)}>Test connection</button>
                  {r && r !== "pending" && <div className={`mt-1 max-w-xs text-xs ${r.ok ? "text-emerald-600" : "text-red-600"}`}>{r.message}</div>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

function Models() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["models"], queryFn: () => get<{ tasks: TaskMapping[]; path: string }>("/settings/models") });
  const [editing, setEditing] = useState<TaskMapping | null>(null);
  const [fallback, setFallback] = useState("");
  const save = useMutation({
    mutationFn: (t: TaskMapping) => put(`/settings/models/${t.task}`, {
      provider: t.provider, model: t.model, fallback: fallback.split(",").map((s) => s.trim()).filter(Boolean),
    }),
    onSuccess: () => { setEditing(null); qc.invalidateQueries({ queryKey: ["models"] }); qc.invalidateQueries({ queryKey: ["providers"] }); },
  });
  if (!data) return <Card title="Models per task"><Skeleton /></Card>;
  return (
    <Card title="Models per task" action={<span className="text-xs text-slate-500">Saved to <code>{data.path.split("/").slice(-2).join("/")}</code></span>}>
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-slate-400"><tr><th>Task</th><th>Provider / model</th><th>Fallbacks</th><th /></tr></thead>
        <tbody>
          {data.tasks.map((t) => editing?.task === t.task ? (
            <tr key={t.task} className="border-t">
              <td className="py-2 font-mono text-xs">{t.task}</td>
              <td className="flex gap-1 py-2">
                <input className="input w-28" value={editing.provider} onChange={(e) => setEditing({ ...editing, provider: e.target.value })} />
                <input className="input" value={editing.model} onChange={(e) => setEditing({ ...editing, model: e.target.value })} />
              </td>
              <td><input className="input" placeholder="provider/model, …" value={fallback} onChange={(e) => setFallback(e.target.value)} /></td>
              <td className="whitespace-nowrap text-right">
                <button className="btn-primary px-2 py-1 text-xs" onClick={() => save.mutate(editing)} disabled={save.isPending}>Save</button>
                <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setEditing(null)}>Cancel</button>
              </td>
            </tr>
          ) : (
            <tr key={t.task} className="border-t">
              <td className="py-2 font-mono text-xs">{t.task}</td>
              <td className="py-2"><code>{t.provider}/{t.model}</code> {!t.priced && <Badge tone="amber">no pricing</Badge>}</td>
              <td className="py-2 text-xs">{t.fallback.join(", ") || "–"}</td>
              <td className="py-2 text-right"><button className="btn-ghost px-2 py-1 text-xs" onClick={() => { setEditing(t); setFallback(t.fallback.join(", ")); }}>Edit</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2"><ErrorBox error={save.error} /></div>
    </Card>
  );
}

function Simulate() {
  const { data: courses = [] } = useCourses();
  const byId = Object.fromEntries(courses.map((c) => [c.id, c]));
  const { data: slots = [] } = useQuery({ queryKey: ["slots"], queryFn: () => get<Slot[]>("/slots") });
  const { data: exams = [] } = useQuery({ queryKey: ["exams"], queryFn: () => get<Exam[]>("/exams") });
  const { data: sessions = [] } = useQuery({ queryKey: ["sessions"], queryFn: () => get<ClassSession[]>("/sessions") });
  const [slotId, setSlotId] = useState("");
  const [examId, setExamId] = useState("");
  const [when, setWhen] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const qc = useQueryClient();
  const note = (m: string) => { setLog((l) => [`${new Date().toLocaleTimeString()} ${m}`, ...l].slice(0, 8)); qc.invalidateQueries(); };
  const emit = useMutation({
    mutationFn: (body: Record<string, unknown>) => post<Job>("/events", body),
    onSuccess: (j) => note(`emitted → job ${j.type} (${j.state})`),
  });
  const tick = useMutation({
    mutationFn: () => post<{ actions: string[] }>("/simulate/tick", when ? { now: new Date(when).toISOString() } : {}),
    onSuccess: (r) => note(`scheduler: ${r.actions.length ? r.actions.join("; ") : "nothing to do"}`),
  });
  const waiting = sessions.filter((s) => s.state === "awaiting_upload");

  return (
    <Card title="Simulate (developer tools)" action={<span className="text-xs text-slate-500">These emit exactly the events the automatic triggers emit.</span>}>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <label className="label">End a class now</label>
          <div className="flex gap-2">
            <select className="input" value={slotId || slots[0]?.id || ""} onChange={(e) => setSlotId(e.target.value)}>
              {slots.map((s) => <option key={s.id} value={s.id}>{byId[s.course_id]?.name} · {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][s.weekday]} {s.start_time}</option>)}
            </select>
            <button className="btn-secondary shrink-0" disabled={!slots.length} onClick={() => emit.mutate({ type: "class_ended", slot_id: slotId || slots[0]?.id })}>class_ended</button>
          </div>
        </div>
        <div className="space-y-2">
          <label className="label">Pending class passes without notes</label>
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-500">{waiting.length ? `${byId[waiting[waiting.length - 1].course_id]?.name} · ${fmtDate(waiting[waiting.length - 1].session_date)}` : "no class waiting"}</span>
            <button className="btn-secondary shrink-0" disabled={!waiting.length} onClick={() => emit.mutate({ type: "class_slot_passed_without_upload" })}>flag missed</button>
          </div>
        </div>
        <div className="space-y-2">
          <label className="label">Exam approaching</label>
          <div className="flex gap-2">
            <select className="input" value={examId || exams[0]?.id || ""} onChange={(e) => setExamId(e.target.value)}>
              {exams.map((x) => <option key={x.id} value={x.id}>{x.title} · {byId[x.course_id]?.name}</option>)}
            </select>
            <button className="btn-secondary shrink-0" disabled={!exams.length} onClick={() => emit.mutate({ type: "exam_approaching", exam_id: examId || exams[0]?.id })}>exam_approaching</button>
          </div>
        </div>
        <div className="space-y-2">
          <label className="label">Run the scheduler at…</label>
          <div className="flex gap-2">
            <input className="input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
            <button className="btn-secondary shrink-0" onClick={() => tick.mutate()}>Run</button>
          </div>
        </div>
      </div>
      <ErrorBox error={emit.error ?? tick.error} />
      {log.length > 0 && <ul className="mt-3 space-y-0.5 font-mono text-xs text-slate-600">{log.map((l, i) => <li key={i}>{l}</li>)}</ul>}
    </Card>
  );
}
