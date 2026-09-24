import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { get } from "../api";
import { Badge, Card, fmtTime, Skeleton, StateBadge, usd } from "../components/ui";
import type { ActivitySummary, AgentRun, AgentStep, LLMCall } from "../types";

function Bars({ data, fmt = (v: number) => String(v) }: { data: Record<string, number>; fmt?: (v: number) => string }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1e-9, ...entries.map(([, v]) => v));
  if (!entries.length) return <p className="text-sm text-slate-500">No data yet.</p>;
  return (
    <ul className="space-y-1.5">
      {entries.map(([k, v]) => (
        <li key={k} className="text-xs">
          <div className="flex justify-between"><span className="font-mono">{k}</span><span>{fmt(v)}</span></div>
          <div className="h-1.5 rounded-full bg-slate-100"><div className="h-1.5 rounded-full bg-indigo-500" style={{ width: `${(v / max) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}

export default function Activity() {
  const [params, setParams] = useSearchParams();
  const runId = params.get("run");
  const summary = useQuery({ queryKey: ["summary"], queryFn: () => get<ActivitySummary>("/activity/summary"), refetchInterval: 10_000 });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => get<AgentRun[]>("/activity/runs?limit=100"), refetchInterval: 10_000 });
  const calls = useQuery({ queryKey: ["llm-calls"], queryFn: () => get<LLMCall[]>("/activity/llm-calls?limit=100"), refetchInterval: 10_000 });
  const s = summary.data;

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Activity & costs</h1>
      {!s ? <Skeleton /> : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {[
            ["Total cost", usd(s.total_cost_usd)], ["LLM calls", `${s.llm_calls}${s.llm_failed_calls ? ` (+${s.llm_failed_calls} failed)` : ""}`],
            ["Deterministic steps", s.deterministic_steps], ["Agent runs", s.agent_runs], ["Unpriced calls", s.unpriced_calls],
          ].map(([k, v]) => (
            <div key={String(k)} className="card p-4"><p className="text-xs uppercase text-slate-500">{k}</p><p className="text-xl font-bold">{v}</p></div>
          ))}
        </div>
      )}
      {s && (
        <div className="grid gap-5 md:grid-cols-3">
          <Card title="Cost by task"><Bars data={s.cost_by_task} fmt={usd} /></Card>
          <Card title="Calls by model"><Bars data={s.calls_by_model} /></Card>
          <Card title="Ingestion paths"><Bars data={s.ingestion_paths} /></Card>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Agent runs">
          <div className="max-h-[32rem] overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-white text-slate-400"><tr><th>When</th><th>Agent</th><th>Goal</th><th>State</th><th>Steps</th><th>Cost</th></tr></thead>
              <tbody>
                {(runs.data ?? []).map((r) => (
                  <tr key={r.id} onClick={() => { params.set("run", r.id); setParams(params); }}
                    className={`cursor-pointer border-t align-top hover:bg-slate-50 ${r.id === runId ? "bg-indigo-50" : ""}`}>
                    <td className="whitespace-nowrap py-1.5">{fmtTime(r.created_at)}</td>
                    <td>{r.agent} {r.mode === "deterministic" && <Badge tone="green">no AI</Badge>}</td>
                    <td className="max-w-[16rem] truncate">{r.goal.split("\n")[0]}</td>
                    <td><StateBadge state={r.state} /></td>
                    <td>{r.steps}</td>
                    <td>{r.cost_usd ? usd(r.cost_usd) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Trace">{runId ? <Trace runId={runId} /> : <p className="text-sm text-slate-500">Select a run to see every step: LLM turns, tool calls and decisions.</p>}</Card>
      </div>
      <Card title="LLM calls">
        <div className="max-h-96 overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-white text-slate-400"><tr><th>When</th><th>Task</th><th>Model</th><th>Tokens in/out</th><th>Cost</th><th>Latency</th><th>Reason</th></tr></thead>
            <tbody>
              {(calls.data ?? []).map((c) => (
                <tr key={c.id} className={`border-t ${c.ok ? "" : "text-red-600"}`}>
                  <td className="whitespace-nowrap py-1">{fmtTime(c.created_at)}</td><td>{c.task}</td>
                  <td className="font-mono">{c.provider}/{c.model} {c.is_fallback && <Badge tone="amber">fallback</Badge>}</td>
                  <td>{c.input_tokens}/{c.output_tokens}</td><td>{c.priced ? usd(c.cost_usd) : <Badge tone="amber">unpriced</Badge>}</td>
                  <td>{c.latency_ms} ms</td><td className="max-w-xs truncate" title={c.error || c.reason}>{c.ok ? c.reason : c.error}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Trace({ runId }: { runId: string }) {
  const { data } = useQuery({
    queryKey: ["run", runId], queryFn: () => get<{ run: AgentRun; steps: AgentStep[]; llm_calls: LLMCall[] }>(`/activity/runs/${runId}`),
    refetchInterval: (q) => (q.state.data?.run.state === "running" ? 2_000 : false),
  });
  if (!data) return <Skeleton />;
  const { run, steps } = data;
  return (
    <div className="space-y-2 text-xs">
      <p><b>{run.agent}</b> · {run.mode} · {run.prompt_version || "no prompt"} · <StateBadge state={run.state} /> · {usd(run.cost_usd)}</p>
      <pre className="whitespace-pre-wrap rounded bg-slate-50 p-2 text-[11px]">{run.goal.slice(0, 600)}{run.goal.length > 600 ? "…" : ""}</pre>
      {run.error && <p className="text-red-600">{run.error}</p>}
      <ol className="max-h-[26rem] space-y-1 overflow-y-auto">
        {steps.map((st) => (
          <li key={st.id} className={`rounded border p-2 ${st.ok ? "" : "border-red-200 bg-red-50"}`}>
            <details>
              <summary className="cursor-pointer">
                <Badge tone={st.kind === "llm" ? "indigo" : st.kind === "tool" ? "blue" : "green"}>{st.kind}</Badge>{" "}
                <span className="font-mono">{st.name}</span> <span className="text-slate-400">{st.latency_ms} ms</span>
              </summary>
              <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap text-[11px]">in: {JSON.stringify(st.input, null, 1)}</pre>
              <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap text-[11px]">out: {JSON.stringify(st.output, null, 1)}</pre>
            </details>
          </li>
        ))}
      </ol>
    </div>
  );
}
