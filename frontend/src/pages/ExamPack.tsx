import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, get, post, put } from "../api";
import { NotFound } from "../App";
import { Badge, Card, ErrorBox, fmtTime, Markdown, Skeleton } from "../components/ui";
import type { Attempt, ExamPackDetail, MockExam, Question } from "../types";

type Cites = ExamPackDetail["citations"];

function Citations({ ids, cites }: { ids: string[]; cites: Cites }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
      <span className="text-slate-400">Sources:</span>
      {ids.map((id) => {
        const c = cites[id];
        return c ? (
          <Link key={id} to={`/subjects/${c.course_id}?topic=${c.topic_id}#${id}`} className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600 hover:bg-indigo-50 hover:text-indigo-700">
            {c.topic_title} › {c.heading}
          </Link>
        ) : <span key={id} className="text-slate-400">(deleted section)</span>;
      })}
    </div>
  );
}

export default function ExamPackPage() {
  const { packId = "" } = useParams();
  const [reveal, setReveal] = useState(false);
  const [tab, setTab] = useState<"guide" | "mocks">("guide");
  const [taking, setTaking] = useState<MockExam | null>(null);
  const pack = useQuery({ queryKey: ["pack", packId, reveal], queryFn: () => get<ExamPackDetail>(`/packs/${packId}?reveal=${reveal}`) });

  if (pack.error instanceof ApiError && pack.error.status === 404) return <NotFound />;
  if (!pack.data) return <Skeleton lines={8} />;
  const p = pack.data;
  if (taking) return <TakeExam mock={taking} cites={p.citations} onExit={() => setTaking(null)} />;

  const printAll = async (withSolutions: boolean) => {
    setReveal(withSolutions);
    setTab("mocks");
    setTimeout(() => window.print(), 600);
  };

  return (
    <div className="space-y-5">
      <div className="no-print flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Exam Pack v{p.version}</h1>
          <p className="text-sm text-slate-500">Built {p.built_at ? fmtTime(p.built_at) : "–"} · trigger {p.trigger} · includes notes up to {p.notes_cutoff ? fmtTime(p.notes_cutoff) : "–"}</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => printAll(false)}>Export PDF</button>
          <button className="btn-secondary" onClick={() => printAll(true)}>Export PDF with solutions</button>
        </div>
      </div>
      <div className="no-print flex gap-1 border-b">
        {(["guide", "mocks"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === t ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500"}`}>
            {t === "guide" ? "Study guide" : `Mock exams (${p.mock_exams.length})`}
          </button>
        ))}
      </div>

      <div className={tab === "guide" ? "" : "hidden print:block"}>
        <Card title="Study guide">
          <div className="space-y-8">
            {p.study_guide.map((g) => (
              <section key={g.id}>
                <h3 className="mb-2 text-lg font-semibold">{g.heading}</h3>
                <Markdown>{g.content_md}</Markdown>
                <Citations ids={g.cited_section_ids} cites={p.citations} />
              </section>
            ))}
          </div>
        </Card>
      </div>

      <div className={tab === "mocks" ? "space-y-5" : "hidden print:block"}>
        {p.mock_exams.map((m) => (
          <Card key={m.id} className="print-break" title={<span>{m.title} <span className="font-normal text-slate-500">· {m.duration_minutes} min · {m.questions.reduce((a, q) => a + q.points, 0)} pts</span></span>}
            action={<button className="btn-primary no-print" onClick={() => setTaking(m)}>Start timed exam</button>}>
            <ol className="space-y-5">
              {m.questions.map((q, i) => <QuestionView key={q.id} q={q} n={i + 1} cites={p.citations} showSolution={reveal} />)}
            </ol>
          </Card>
        ))}
        <label className="no-print flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={reveal} onChange={(e) => setReveal(e.target.checked)} /> Show solutions (spoilers)
        </label>
      </div>
    </div>
  );
}

function QuestionView({ q, n, cites, showSolution, score, onScore }: {
  q: Question; n: number; cites: Cites; showSolution: boolean; score?: number; onScore?: (v: number) => void;
}) {
  return (
    <li className="rounded-lg border p-4">
      <div className="mb-1 flex items-center justify-between text-sm">
        <b>Question {n}</b>
        <span className="flex items-center gap-2">
          {q.state === "verified" && <Badge tone="green">verified</Badge>}
          <span className="text-slate-500">{q.points} pts</span>
        </span>
      </div>
      <Markdown>{q.statement_md}</Markdown>
      {showSolution && q.solution_md && (
        <div className="mt-3 rounded-lg bg-emerald-50/60 p-3">
          <p className="mb-1 text-xs font-semibold uppercase text-emerald-700">Solution</p>
          <Markdown>{q.solution_md}</Markdown>
          {q.rubric && (
            <table className="mt-2 w-full text-sm">
              <tbody>{q.rubric.map((r, i) => <tr key={i} className="border-t"><td className="py-1">{r.criterion}</td><td className="text-right">{r.points} pts</td></tr>)}</tbody>
            </table>
          )}
          {onScore && (
            <label className="mt-2 flex items-center gap-2 text-sm">Your score:
              <input type="number" min={0} max={q.points} step={0.5} className="input w-24" value={score ?? ""} onChange={(e) => onScore(Number(e.target.value))} /> / {q.points}
            </label>
          )}
        </div>
      )}
      <Citations ids={q.cited_section_ids} cites={cites} />
    </li>
  );
}

function TakeExam({ mock, cites, onExit }: { mock: MockExam; cites: Cites; onExit: () => void }) {
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [scores, setScores] = useState<Record<string, number>>({});
  const [left, setLeft] = useState(mock.duration_minutes * 60);
  const start = useMutation({ mutationFn: () => post<Attempt>(`/mock-exams/${mock.id}/attempts`), onSuccess: setAttempt });
  const submit = useMutation({
    mutationFn: () => put<Attempt>(`/attempts/${attempt!.id}`, { answers, submit: true }),
    onSuccess: setAttempt,
  });
  const saveScores = useMutation({ mutationFn: () => put<Attempt>(`/attempts/${attempt!.id}`, { self_scores: scores, submit: true }) });
  const solved = useQuery({
    queryKey: ["mock", mock.id, "reveal"], enabled: Boolean(attempt?.submitted_at),
    queryFn: () => get<MockExam>(`/mock-exams/${mock.id}?reveal=true`),
  });
  const submitted = Boolean(attempt?.submitted_at);

  useEffect(() => {
    if (!attempt || submitted) return;
    const t = setInterval(() => setLeft((s) => s - 1), 1000);
    return () => clearInterval(t);
  }, [attempt, submitted]);
  useEffect(() => {
    if (attempt && !submitted && left <= 0 && !submit.isPending) submit.mutate();
  }, [left, attempt, submitted, submit]);

  const mm = String(Math.max(0, Math.floor(left / 60))).padStart(2, "0");
  const ss = String(Math.max(0, left % 60)).padStart(2, "0");
  const total = mock.questions.reduce((a, q) => a + q.points, 0);
  const got = Object.values(scores).reduce((a, b) => a + (b || 0), 0);

  return (
    <div className="space-y-4">
      <div className="sticky top-0 z-10 flex items-center justify-between rounded-xl border bg-white p-3 shadow-sm">
        <div><b>{mock.title}</b> <span className="text-sm text-slate-500">· {total} pts</span></div>
        <div className="flex items-center gap-3">
          {attempt && !submitted && <span className={`font-mono text-xl ${left < 300 ? "text-red-600" : ""}`}>{mm}:{ss}</span>}
          {submitted && <span className="text-sm">Self-score: <b>{got}</b> / {total}</span>}
          <button className="btn-ghost" onClick={onExit}>Exit</button>
        </div>
      </div>
      {!attempt ? (
        <Card>
          <p className="text-sm">Timed mode: {mock.duration_minutes} minutes, {mock.questions.length} questions. Solutions appear after you submit. The exam submits automatically when time runs out.</p>
          <button className="btn-primary mt-3" onClick={() => start.mutate()} disabled={start.isPending}>Start now</button>
          <ErrorBox error={start.error} />
        </Card>
      ) : (
        <ol className="space-y-4">
          {(submitted ? solved.data?.questions ?? mock.questions : mock.questions).map((q, i) => (
            <div key={q.id} className="space-y-2">
              <QuestionView q={q} n={i + 1} cites={cites} showSolution={submitted}
                score={scores[q.id]} onScore={(v) => setScores((s) => ({ ...s, [q.id]: v }))} />
              <textarea className="input h-32 font-mono" placeholder="Your answer (Markdown / LaTeX allowed)" disabled={submitted}
                value={answers[q.id] ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))} />
            </div>
          ))}
        </ol>
      )}
      {attempt && !submitted && <button className="btn-primary" onClick={() => submit.mutate()} disabled={submit.isPending}>Submit exam</button>}
      {submitted && <button className="btn-secondary" onClick={() => saveScores.mutate()} disabled={saveScores.isPending}>{saveScores.isSuccess ? "Scores saved" : "Save my scores"}</button>}
      <ErrorBox error={submit.error ?? saveScores.error} />
    </div>
  );
}
