import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { get, post } from "../api";
import { useMe } from "../App";
import { useCourses } from "../components/editors";
import { Badge, Card, daysUntil, Empty, ErrorBox, fmtDate, fmtTime, Skeleton, StateBadge } from "../components/ui";
import type { ClassSession, Exam, ExamPack, FeedItem, Slot } from "../types";

export default function Today() {
  const { data: me } = useMe();
  const { data: courses = [] } = useCourses();
  const byId = Object.fromEntries(courses.map((c) => [c.id, c]));
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => get<ClassSession[]>("/sessions?limit=60"), refetchInterval: 15_000 });
  const { data: slots = [] } = useQuery({ queryKey: ["slots"], queryFn: () => get<Slot[]>("/slots") });
  const { data: exams = [] } = useQuery({ queryKey: ["exams"], queryFn: () => get<Exam[]>("/exams") });
  const { data: packs = [] } = useQuery({ queryKey: ["packs"], queryFn: () => get<ExamPack[]>("/packs"), refetchInterval: 10_000 });
  const feed = useQuery({ queryKey: ["feed"], queryFn: () => get<FeedItem[]>("/activity/feed?limit=15"), refetchInterval: 10_000 });
  const qc = useQueryClient();
  const build = useMutation({
    mutationFn: (examId: string) => post(`/exams/${examId}/build-pack`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["packs"] }),
  });

  const pending = (sessions.data ?? []).filter((s) => s.state === "awaiting_upload" || s.state === "missed");
  const todayIdx = (new Date().getDay() + 6) % 7;
  const now = new Date();
  const hhmm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  const todays = slots.filter((s) => s.weekday === todayIdx);
  const upcoming = exams.filter((e) => daysUntil(e.exam_date) >= 0);
  const firstRun = (sessions.data ?? []).length === 0 && (feed.data ?? []).length === 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Hi {me?.display_name?.split(" ")[0] || "there"} 👋</h1>
        <p className="text-sm text-slate-500">{now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</p>
      </div>

      {firstRun && (
        <div className="card border-indigo-200 bg-indigo-50/50">
          <h2 className="font-semibold">How Studilo works</h2>
          <ol className="mt-2 grid gap-3 text-sm text-slate-600 md:grid-cols-3">
            <li><b>1. After each class</b> you get a prompt: upload your notes (PDF, photo or text).</li>
            <li><b>2. Studilo organises them</b> into topic notes and a course memory, with sources.</li>
            <li><b>3. Before exams</b> an Exam Pack appears: study guide + mock exams from your notes.</li>
          </ol>
        </div>
      )}

      <Card title="Pending uploads" action={<Link to="/upload" className="btn-secondary">Upload</Link>}>
        {sessions.isLoading ? <Skeleton /> : pending.length === 0 ? (
          <p className="text-sm text-slate-500">All caught up — no notes pending.</p>
        ) : (
          <ul className="divide-y">
            {pending.map((s) => (
              <li key={s.id} className="flex items-center justify-between py-2">
                <span className="text-sm">
                  <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: byId[s.course_id]?.color }} />
                  <b>{byId[s.course_id]?.name}</b> · {fmtDate(s.session_date, { weekday: "short", day: "numeric", month: "short" })}
                  {s.state === "missed" && <span className="ml-2"><Badge tone="red">missed</Badge></span>}
                </span>
                <Link className="btn-primary" to={`/upload?session=${s.id}&course=${s.course_id}`}>Upload notes</Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="grid gap-5 md:grid-cols-2">
        <Card title="Today's classes">
          {todays.length === 0 ? <p className="text-sm text-slate-500">No classes today.</p> : (
            <ul className="space-y-2">
              {todays.map((s) => {
                const status = hhmm < s.start_time ? "upcoming" : hhmm < s.end_time ? "in progress" : "ended";
                return (
                  <li key={s.id} className="flex items-center justify-between text-sm">
                    <span><b>{s.start_time}–{s.end_time}</b> {byId[s.course_id]?.name}</span>
                    <Badge tone={status === "in progress" ? "blue" : status === "ended" ? "gray" : "indigo"}>{status}</Badge>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="Upcoming exams" action={<Link to="/exams" className="text-sm text-indigo-600">Manage</Link>}>
          {upcoming.length === 0 ? <p className="text-sm text-slate-500">No exams yet — add one in Exams.</p> : (
            <ul className="space-y-3">
              {upcoming.map((e) => {
                const pack = packs.find((p) => p.exam_id === e.id);
                const days = daysUntil(e.exam_date);
                return (
                  <li key={e.id} className="flex items-center justify-between gap-2">
                    <div className="text-sm">
                      <div><b>{e.title}</b> · {byId[e.course_id]?.name}</div>
                      <div className="text-slate-500">{fmtDate(e.exam_date, { dateStyle: "medium" })}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`rounded-lg px-2 py-1 text-lg font-bold ${days <= 3 ? "bg-red-50 text-red-600" : days <= 7 ? "bg-amber-50 text-amber-700" : "bg-slate-100"}`}>{days}d</span>
                      {pack ? (
                        pack.state === "ready" ? <Link className="btn-secondary" to={`/packs/${pack.id}`}>Pack v{pack.version}</Link> : <StateBadge state={pack.state} />
                      ) : (
                        <button className="btn-secondary" disabled={build.isPending} onClick={() => build.mutate(e.id)}>Build pack now</button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          <ErrorBox error={build.error} />
        </Card>
      </div>

      <Card title="Agent activity" action={<Link to="/activity" className="text-sm text-indigo-600">All activity & costs</Link>}>
        {feed.isLoading ? <Skeleton /> : (feed.data ?? []).length === 0 ? (
          <Empty title="No agent activity yet">It starts when a class ends or you upload notes.</Empty>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {(feed.data ?? []).map((f, i) => (
              <li key={i} className="flex gap-3">
                <span className="w-28 shrink-0 text-xs text-slate-400">{fmtTime(f.at)}</span>
                {f.link ? <Link to={f.link} className="hover:text-indigo-600">{f.text}</Link> : <span className="text-slate-600">{f.text}</span>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
