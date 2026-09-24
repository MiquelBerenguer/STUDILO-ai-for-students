import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { get, post } from "../api";
import { ExamsEditor, useCourses } from "../components/editors";
import { Card, daysUntil, Empty, ErrorBox, fmtDate, fmtTime, Spinner, StateBadge } from "../components/ui";
import type { Exam, ExamPack, Job } from "../types";

export default function Exams() {
  const { data: courses = [] } = useCourses();
  const byId = Object.fromEntries(courses.map((c) => [c.id, c]));
  const { data: exams = [] } = useQuery({ queryKey: ["exams"], queryFn: () => get<Exam[]>("/exams") });
  const packs = useQuery({
    queryKey: ["packs"], queryFn: () => get<ExamPack[]>("/packs"),
    refetchInterval: (q) => (q.state.data?.some((p) => p.state === "building" || p.state === "pending") ? 3_000 : 15_000),
  });
  const jobs = useQuery({
    queryKey: ["jobs", "build"], queryFn: () => get<Job[]>("/jobs?limit=40"),
    refetchInterval: 3_000,
  });
  const qc = useQueryClient();
  const build = useMutation({
    mutationFn: (examId: string) => post<Job>(`/exams/${examId}/build-pack`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["jobs"] }); qc.invalidateQueries({ queryKey: ["packs"] }); },
  });
  const retry = useMutation({
    mutationFn: (jobId: string) => post<Job>(`/jobs/${jobId}/retry`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const buildJobs = (jobs.data ?? []).filter((j) => j.type === "build_exam_pack");
  const activeFor = (examId: string | null, courseId: string) => buildJobs.find((j) =>
    (j.state === "queued" || j.state === "running") && (examId ? j.payload.exam_id === examId : j.payload.course_id === courseId));
  const failedFor = (examId: string) => buildJobs.find((j) => j.state === "failed" && j.payload.exam_id === examId);
  const practicePacks = (packs.data ?? []).filter((p) => !p.exam_id);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Exams</h1>
      {exams.length === 0 && <Empty title="No exams yet">Add one below — packs are built automatically 14, 7 and 3 days before.</Empty>}
      {exams.map((e) => {
        const ps = (packs.data ?? []).filter((p) => p.exam_id === e.id);
        const active = activeFor(e.id, e.course_id);
        const failed = failedFor(e.id);
        const days = daysUntil(e.exam_date);
        return (
          <Card key={e.id} title={<span>{e.title} <span className="font-normal text-slate-500">· {byId[e.course_id]?.name}</span></span>}
            action={<button className="btn-primary" disabled={Boolean(active) || build.isPending} onClick={() => build.mutate(e.id)}>{ps.length ? "Refresh pack" : "Build pack now"}</button>}>
            <p className="text-sm text-slate-500">{fmtDate(e.exam_date, { dateStyle: "full" })} · {days >= 0 ? `in ${days} days` : `${-days} days ago`}{e.scope_note && ` · Scope: ${e.scope_note}`}</p>
            {active && <p className="mt-2 flex items-center gap-2 text-sm text-sky-700"><Spinner /> {active.progress || "Queued — the Exam agent will start shortly"}</p>}
            {failed && !active && (
              <div className="mt-2 flex items-center gap-2"><ErrorBox error={failed.error} /><button className="btn-secondary" onClick={() => retry.mutate(failed.id)}>Retry</button></div>
            )}
            {ps.length === 0 && !active && <p className="mt-2 text-sm text-slate-500">No pack yet: it will be built automatically 14 days before the exam, or build it now.</p>}
            <ul className="mt-3 divide-y">
              {ps.map((p) => <PackRow key={p.id} p={p} />)}
            </ul>
          </Card>
        );
      })}
      {practicePacks.length > 0 && (
        <Card title="Practice exams (on demand)">
          <ul className="divide-y">{practicePacks.map((p) => <PackRow key={p.id} p={p} label={byId[p.course_id]?.name} />)}</ul>
        </Card>
      )}
      <ErrorBox error={build.error} />
      <Card title="Add or remove exams"><ExamsEditor /></Card>
    </div>
  );
}

function PackRow({ p, label }: { p: ExamPack; label?: string }) {
  return (
    <li className="flex items-center justify-between py-2 text-sm">
      <span>{label && <b className="mr-2">{label}</b>}Pack v{p.version} · trigger {p.trigger} · {fmtTime(p.created_at)} <StateBadge state={p.state} /></span>
      {p.state === "ready" ? <Link className="btn-secondary" to={`/packs/${p.id}`}>Open</Link> : p.state === "failed" ? <span className="max-w-md truncate text-xs text-red-600">{p.error}</span> : <Spinner />}
    </li>
  );
}
