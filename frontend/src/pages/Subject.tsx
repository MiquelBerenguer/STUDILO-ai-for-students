import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ApiError, get, post } from "../api";
import { NotFound } from "../App";
import { Badge, Card, Empty, ErrorBox, fmtDate, fmtTime, Markdown, Skeleton, StateBadge } from "../components/ui";
import type { Course, CourseMemory, Job, SearchHit, Topic, TopicNote, Upload } from "../types";

type Tab = "notes" | "memory" | "sources";

export default function Subject() {
  const { courseId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "notes";
  const course = useQuery({ queryKey: ["course", courseId], queryFn: () => get<Course>(`/courses/${courseId}`) });
  const memory = useQuery({ queryKey: ["memory", courseId], queryFn: () => get<CourseMemory>(`/courses/${courseId}/memory`) });
  const navigate = useNavigate();
  const practice = useMutation({
    mutationFn: () => post<Job>(`/courses/${courseId}/practice-exam`),
    onSuccess: () => navigate("/exams"),
  });

  if (course.error instanceof ApiError && course.error.status === 404) return <NotFound />;
  if (!course.data) return <Skeleton lines={6} />;
  const setTab = (t: Tab) => { params.set("tab", t); setParams(params); };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <span className="h-4 w-4 rounded-full" style={{ background: course.data.color }} />{course.data.name}
          </h1>
          {memory.data && (
            <p className="text-sm text-slate-500">
              {memory.data.topics_per_week} topics/week{memory.data.syllabus_position && ` · ${memory.data.syllabus_position}`}
              {memory.data.missed_count > 0 && <span className="ml-2"><Badge tone="red">{memory.data.missed_count} missed</Badge></span>}
            </p>
          )}
        </div>
        <button className="btn-primary" disabled={practice.isPending} onClick={() => practice.mutate()}>Practice exam</button>
      </div>
      <ErrorBox error={practice.error} />
      <div className="flex gap-1 border-b">
        {(["notes", "memory", "sources"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === t ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500"}`}>
            {t === "notes" ? "Notes" : t === "memory" ? "Course memory" : "Sources"}
          </button>
        ))}
      </div>
      {tab === "notes" && <NotesTab courseId={courseId} />}
      {tab === "memory" && <MemoryTab courseId={courseId} memory={memory.data} />}
      {tab === "sources" && <SourcesTab courseId={courseId} />}
    </div>
  );
}

function NotesTab({ courseId }: { courseId: string }) {
  const [params, setParams] = useSearchParams();
  const topics = useQuery({ queryKey: ["topics", courseId], queryFn: () => get<Topic[]>(`/courses/${courseId}/topics`) });
  const selected = params.get("topic") || topics.data?.[0]?.id || "";
  const note = useQuery({
    queryKey: ["note", selected], enabled: Boolean(selected),
    queryFn: () => get<TopicNote>(`/topics/${selected}/note`),
  });
  const [q, setQ] = useState("");
  const search = useMutation({ mutationFn: () => get<SearchHit[]>(`/notes/search?q=${encodeURIComponent(q)}&course_id=${courseId}`) });

  if (topics.isLoading) return <Skeleton lines={5} />;
  if (!topics.data?.length) {
    return <Empty title="No notes yet">Upload notes after your next class — <Link className="text-indigo-600" to={`/upload?course=${courseId}`}>upload now</Link>.</Empty>;
  }
  const children = (pid: string | null) => topics.data!.filter((t) => t.parent_id === pid);
  const pick = (id: string) => { params.set("topic", id); setParams(params); };
  const renderTree = (pid: string | null, depth = 0): React.ReactNode => children(pid).map((t) => (
    <div key={t.id}>
      <button onClick={() => pick(t.id)} style={{ paddingLeft: 8 + depth * 14 }}
        className={`flex w-full justify-between rounded-md py-1.5 pr-2 text-left text-sm ${t.id === selected ? "bg-indigo-50 font-medium text-indigo-700" : "hover:bg-slate-100"}`}>
        <span>{t.title}</span><span className="text-xs text-slate-400">{t.section_count}</span>
      </button>
      {renderTree(t.id, depth + 1)}
    </div>
  ));

  return (
    <div className="grid gap-5 md:grid-cols-[240px_1fr]">
      <div className="space-y-3">
        <form onSubmit={(e) => { e.preventDefault(); if (q.trim().length > 1) search.mutate(); }}>
          <input className="input" placeholder="Search these notes…" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
        {search.data && (
          <div className="rounded-lg border bg-white p-2 text-sm">
            {search.data.length === 0 ? <p className="text-slate-500">No matches.</p> : search.data.map((h) => (
              <button key={h.section_id} className="block w-full rounded p-1 text-left hover:bg-slate-50" onClick={() => { pick(h.topic_id); setTimeout(() => document.getElementById(h.section_id)?.scrollIntoView({ behavior: "smooth" }), 300); }}>
                <div className="font-medium">{h.topic_title} › {h.heading}</div>
                <div className="line-clamp-2 text-xs text-slate-500">{h.snippet}</div>
              </button>
            ))}
          </div>
        )}
        <nav className="rounded-lg border bg-white p-1">{renderTree(null)}</nav>
      </div>
      <div>
        {note.isLoading || !note.data ? <Skeleton lines={8} /> : (
          <article className="card space-y-6">
            <header>
              <h2 className="text-xl font-semibold">{note.data.topic.title}</h2>
              {note.data.topic.summary && <p className="text-sm text-slate-500">{note.data.topic.summary}</p>}
            </header>
            {note.data.sections.map((s) => (
              <section key={s.id} id={s.id} className="scroll-mt-20">
                <h3 className="mb-2 text-lg font-semibold">{s.heading}</h3>
                <Markdown>{s.content_md}</Markdown>
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                  <span className="text-slate-400">Sources:</span>
                  {s.sources.map((src) => (
                    <a key={src.upload_id} href={`/api/v1/uploads/${src.upload_id}/file`} target="_blank" rel="noreferrer"
                      className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600 hover:bg-indigo-50 hover:text-indigo-700">
                      📄 {src.filename} · {fmtDate(src.created_at)}
                    </a>
                  ))}
                  {s.version > 1 && <span className="text-slate-400">· revised {s.version - 1}×</span>}
                </div>
              </section>
            ))}
          </article>
        )}
      </div>
    </div>
  );
}

function MemoryTab({ courseId, memory }: { courseId: string; memory?: CourseMemory }) {
  const topics = useQuery({ queryKey: ["topics", courseId], queryFn: () => get<Topic[]>(`/courses/${courseId}/topics`) });
  const qc = useQueryClient();
  const resolve = useMutation({
    mutationFn: (id: string) => post(`/open-questions/${id}/resolve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memory", courseId] }),
  });
  if (!memory) return <Skeleton lines={6} />;
  const title = Object.fromEntries((topics.data ?? []).map((t) => [t.id, t.title]));
  const open = memory.open_questions.filter((q) => q.status === "open");

  return (
    <div className="grid gap-5 md:grid-cols-3">
      <Card title="Sessions" className="md:col-span-2">
        {memory.sessions.length === 0 ? <p className="text-sm text-slate-500">No class sessions yet. They appear when a class ends.</p> : (
          <ol className="relative space-y-4 border-l border-slate-200 pl-5">
            {memory.sessions.map((s) => (
              <li key={s.id} className="relative">
                <span className={`absolute -left-[27px] top-1 h-3 w-3 rounded-full ring-4 ring-white ${s.state === "missed" ? "bg-red-500" : s.state === "processed" ? "bg-emerald-500" : "bg-amber-400"}`} />
                <div className="flex items-center gap-2 text-sm">
                  <b>{fmtDate(s.session_date, { weekday: "short", day: "numeric", month: "short" })}</b>
                  <StateBadge state={s.state} />
                  {s.state === "missed" && <Link className="text-xs text-indigo-600" to={`/upload?session=${s.id}&course=${courseId}`}>upload late notes</Link>}
                </div>
                {s.missed_reason && s.state === "missed" && <p className="text-xs text-red-600">{s.missed_reason}</p>}
                {s.summary_md && <Markdown className="prose-sm mt-1">{s.summary_md}</Markdown>}
                {s.topic_ids.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{s.topic_ids.map((t) => <Badge key={t} tone="indigo">{title[t] ?? "topic"}</Badge>)}</div>}
              </li>
            ))}
          </ol>
        )}
      </Card>
      <div className="space-y-5">
        <Card title="Pace">
          <p className="text-3xl font-bold">{memory.topics_per_week}<span className="text-sm font-normal text-slate-500"> topics / week</span></p>
          {memory.syllabus_position && <p className="mt-1 text-sm">{memory.syllabus_position}</p>}
          {memory.pace_note && <p className="mt-1 text-xs text-slate-500">{memory.pace_note}</p>}
          <p className="mt-2 text-xs text-slate-500">{memory.missed_count} missed session(s)</p>
        </Card>
        <Card title="Builds on">
          {memory.dependencies.length === 0 ? <p className="text-sm text-slate-500">No dependencies recorded yet.</p> : (
            <ul className="space-y-1 text-sm">{memory.dependencies.map((d, i) => <li key={i}>{title[d.topic_id]} <span className="text-slate-400">← builds on</span> {title[d.depends_on_id]}</li>)}</ul>
          )}
        </Card>
        <Card title={`Open questions (${open.length})`}>
          {open.length === 0 ? <p className="text-sm text-slate-500">No open doubts.</p> : (
            <ul className="space-y-2 text-sm">{open.map((q) => (
              <li key={q.id} className="flex items-start justify-between gap-2">
                <span>{q.text}</span>
                <button className="btn-ghost shrink-0 px-2 py-1 text-xs" onClick={() => resolve.mutate(q.id)}>Resolve</button>
              </li>
            ))}</ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function SourcesTab({ courseId }: { courseId: string }) {
  const { data = [], isLoading } = useQuery({ queryKey: ["uploads", courseId], queryFn: () => get<Upload[]>(`/uploads?course_id=${courseId}&limit=200`) });
  if (isLoading) return <Skeleton />;
  if (!data.length) return <Empty title="No files uploaded for this subject yet" />;
  return (
    <div className="card overflow-x-auto p-0">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="p-3">File</th><th>Kind</th><th>Uploaded</th><th>Status</th><th /></tr></thead>
        <tbody>
          {data.map((u) => (
            <tr key={u.id} className="border-t">
              <td className="p-3">{u.filename} <span className="text-xs text-slate-400">{u.detected_type}</span></td>
              <td>{u.kind === "past_exam" ? "past exam" : "notes"}</td>
              <td>{fmtTime(u.created_at)}</td>
              <td><StateBadge state={u.state} /> <span className="text-xs text-slate-500">{u.status_message}</span></td>
              <td className="pr-3 text-right"><a className="text-indigo-600" href={`/api/v1/uploads/${u.id}/file`} target="_blank" rel="noreferrer">Open</a></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
