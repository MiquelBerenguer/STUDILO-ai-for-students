import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { type DragEvent, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, get, post } from "../api";
import { useCourses } from "../components/editors";
import { Badge, Card, ErrorBox, fmtDate, fmtTime, Spinner, StateBadge, usd } from "../components/ui";
import type { ClassSession, Upload, UploadDetail } from "../types";

const STAGES: { key: string; label: string }[] = [
  { key: "received", label: "Received" },
  { key: "extracting", label: "Reading" },
  { key: "classifying", label: "Topic" },
  { key: "structuring", label: "Notes" },
  { key: "updating_memory", label: "Memory" },
  { key: "done", label: "Done" },
];

export default function UploadPage() {
  const [params] = useSearchParams();
  const sessionParam = params.get("session");
  const { data: courses = [] } = useCourses();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => get<ClassSession[]>("/sessions?limit=100") });
  const preSession = sessions.data?.find((s) => s.id === sessionParam);
  const [courseId, setCourseId] = useState(params.get("course") ?? "");
  const [sessionId, setSessionId] = useState(sessionParam ?? "");
  const [kind, setKind] = useState<"notes" | "past_exam">("notes");
  const [drag, setDrag] = useState(false);
  const [mine, setMine] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const camRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  useEffect(() => {
    if (preSession && !courseId) setCourseId(preSession.course_id);
  }, [preSession, courseId]);
  const cid = courseId || courses[0]?.id || "";
  const courseSessions = (sessions.data ?? []).filter((s) => s.course_id === cid);

  const send = useMutation({
    mutationFn: async (files: File[]) => {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      fd.append("course_id", cid);
      fd.append("kind", kind);
      if (sessionId && courseSessions.some((s) => s.id === sessionId)) fd.append("class_session_id", sessionId);
      return api<Upload[]>("/uploads", { method: "POST", body: fd });
    },
    onSuccess: (ups) => {
      setMine((m) => [...ups.map((u) => u.id), ...m]);
      qc.invalidateQueries({ queryKey: ["uploads"] });
    },
  });
  const recent = useQuery({ queryKey: ["uploads"], queryFn: () => get<Upload[]>("/uploads?limit=10"), refetchInterval: 5_000 });

  function onFiles(list: FileList | null) {
    if (list && list.length) send.mutate(Array.from(list));
  }
  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDrag(false);
    onFiles(e.dataTransfer.files);
  }

  const shown = [...new Set([...mine, ...(recent.data ?? []).map((u) => u.id)])].slice(0, 12);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Upload notes</h1>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <label className="label">Subject</label>
              <select className="input" value={cid} onChange={(e) => { setCourseId(e.target.value); setSessionId(""); }}>
                {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Which class</label>
              <select className="input" value={sessionId} onChange={(e) => setSessionId(e.target.value)} disabled={kind === "past_exam"}>
                <option value="">No specific class (today)</option>
                {courseSessions.map((s) => (
                  <option key={s.id} value={s.id}>{fmtDate(s.session_date, { weekday: "short", day: "numeric", month: "short" })} · {s.state.replace("_", " ")}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Kind</label>
              <div className="flex rounded-lg border p-0.5">
                {(["notes", "past_exam"] as const).map((k) => (
                  <button key={k} className={`flex-1 rounded-md px-2 py-1.5 text-sm ${kind === k ? "bg-indigo-600 text-white" : "text-slate-600"}`} onClick={() => setKind(k)}>
                    {k === "notes" ? "Class notes" : "Past exam"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            className={`mt-4 flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition ${drag ? "border-indigo-500 bg-indigo-50" : "border-slate-300"}`}
          >
            <p className="font-medium">Drop PDFs, photos or text files here</p>
            <p className="text-sm text-slate-500">PDF · JPG · PNG · HEIC · TXT/MD — several at once</p>
            <div className="mt-4 flex gap-2">
              <button className="btn-primary" disabled={!cid || send.isPending} onClick={() => fileRef.current?.click()}>Choose files</button>
              <button className="btn-secondary" disabled={!cid || send.isPending} onClick={() => camRef.current?.click()}>Take photo</button>
            </div>
            <input ref={fileRef} type="file" multiple hidden accept=".pdf,image/*,.heic,.txt,.md,text/plain" onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }} />
            <input ref={camRef} type="file" hidden accept="image/*" capture="environment" onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }} />
            {send.isPending && <p className="mt-3 flex items-center gap-2 text-sm text-slate-500"><Spinner /> Uploading…</p>}
          </div>
          <div className="mt-3"><ErrorBox error={send.error} /></div>
        </Card>
        <PhonePanel />
      </div>

      <Card title="Progress">
        {shown.length === 0 ? <p className="text-sm text-slate-500">Uploads will appear here with live progress.</p> : (
          <ul className="space-y-3">{shown.map((id) => <UploadRow key={id} id={id} />)}</ul>
        )}
      </Card>
    </div>
  );
}

function PhonePanel() {
  const { data } = useQuery({ queryKey: ["lan", location.port], queryFn: () => get<{ urls: string[] }>(`/settings/lan?port=${location.port || 80}`) });
  const url = data?.urls[0] ? `${data.urls[0]}/upload` : null;
  return (
    <Card title="On your phone">
      {url ? (
        <div className="flex flex-col items-center gap-2 text-center">
          <QRCodeSVG value={url} size={148} />
          <code className="break-all text-xs">{url}</code>
          <p className="text-xs text-slate-500">Open this on your phone — same Wi-Fi. Log in, then use “Take photo”.</p>
        </div>
      ) : <p className="text-sm text-slate-500">No LAN address found. Connect to Wi-Fi and run <code>make dev</code> (it serves on your LAN).</p>}
    </Card>
  );
}

function UploadRow({ id }: { id: string }) {
  const qc = useQueryClient();
  const { data: u } = useQuery({
    queryKey: ["upload", id],
    queryFn: () => get<UploadDetail>(`/uploads/${id}`),
    refetchInterval: (q) => (q.state.data && ["done", "failed"].includes(q.state.data.state) ? false : 1_200),
  });
  const retry = useMutation({ mutationFn: () => post(`/uploads/${id}/retry`), onSuccess: () => qc.invalidateQueries({ queryKey: ["upload", id] }) });
  if (!u) return <li className="text-sm text-slate-400"><Spinner /></li>;
  const idx = STAGES.findIndex((s) => s.key === u.state);
  const stages = u.kind === "past_exam" ? STAGES.filter((s) => !["structuring", "updating_memory"].includes(s.key)) : STAGES;
  const warn = u.status_message.includes("warning");
  const llm = u.log.filter((l) => l.model_used && l.cost_usd > 0);
  return (
    <li className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium">{u.filename} <span className="text-xs text-slate-400">{u.detected_type} · {(u.size_bytes / 1024).toFixed(0)} KB · {fmtTime(u.created_at)}</span></span>
        <span className="flex items-center gap-2">
          {u.kind === "past_exam" && <Badge tone="indigo">past exam</Badge>}
          {llm.length === 0 && u.state === "done" && <Badge tone="green">no AI needed to read</Badge>}
          <StateBadge state={u.state} />
        </span>
      </div>
      {u.state !== "failed" && (
        <div className="mt-2 flex gap-1">
          {stages.map((s) => {
            const pos = STAGES.findIndex((x) => x.key === s.key);
            return <div key={s.key} className="flex-1">
              <div className={`h-1.5 rounded-full ${pos < idx || u.state === "done" ? "bg-indigo-600" : pos === idx ? "animate-pulse bg-indigo-400" : "bg-slate-200"}`} />
              <div className="mt-0.5 text-[10px] text-slate-400">{s.label}</div>
            </div>;
          })}
        </div>
      )}
      <p className={`mt-1 text-sm ${u.state === "failed" ? "text-red-600" : warn ? "text-amber-700" : "text-slate-600"}`}>{u.status_message}</p>
      {u.state === "failed" && <button className="btn-secondary mt-2" onClick={() => retry.mutate()}>Retry</button>}
      {u.state === "done" && u.topic_id && <Link className="text-sm text-indigo-600" to={`/subjects/${u.course_id}?topic=${u.topic_id}`}>Open the notes →</Link>}
      {u.log.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-slate-500">How was this read?</summary>
          <table className="mt-2 w-full text-left text-xs">
            <thead className="text-slate-400"><tr><th>Page</th><th>Step</th><th>Path</th><th>Why</th><th>Scores</th><th>Model</th><th>Cost</th></tr></thead>
            <tbody>
              {u.log.map((l) => (
                <tr key={l.id} className="border-t align-top">
                  <td>{l.page ?? "–"}</td><td>{l.step}</td><td className="font-mono">{l.path_taken}</td><td>{l.reason}</td>
                  <td>{l.legibility_score != null && `legibility ${l.legibility_score}`}{l.ocr_confidence != null && `OCR ${l.ocr_confidence}`}</td>
                  <td>{l.model_used ?? "–"}{l.tokens_in ? ` (${l.tokens_in}/${l.tokens_out} tok)` : ""}</td>
                  <td>{l.cost_usd ? usd(l.cost_usd) : "no AI"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </li>
  );
}
