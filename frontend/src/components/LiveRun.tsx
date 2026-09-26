// Live agent run (UX.md §5): which agent, the step it is on in plain language, the result. Expandable.
// Every line comes from a persisted agent_step; nothing is animated without a running agent_run.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { get, post } from "../api";
import type { LiveRunT } from "../types";
import { clock } from "../hooks";
import { Icon } from "./icons";
import { usd } from "./ui";

function elapsed(run: LiveRunT): string {
  const end = run.finished_at ? new Date(run.finished_at).getTime() : Date.now();
  const s = Math.max(0, Math.round((end - new Date(run.created_at).getTime()) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function LiveRun({ run, defaultOpen, compact }: { run: LiveRunT; defaultOpen?: boolean; compact?: boolean }) {
  const running = run.state === "running";
  const [open, setOpen] = useState(defaultOpen ?? running);
  const [undoMsg, setUndoMsg] = useState<string | null>(null);
  const qc = useQueryClient();
  // Feed lists finished runs without steps; load the trace when the student expands one.
  const { data: detail } = useQuery({
    queryKey: ["run", run.id],
    queryFn: () => get<LiveRunT>(`/runs/${run.id}`),
    enabled: open && !running && run.steps.length === 0,
    staleTime: Infinity,
  });
  const steps = run.steps.length ? run.steps : detail?.steps ?? [];
  const visible = open ? steps : steps.slice(-1);
  const noAi = run.llm_calls === 0 && run.state === "succeeded"; // a failed run may have tried AI and failed

  async function undo() {
    try {
      const r = await post<{ message: string }>(`/actions/${run.undo_action_id}/undo`);
      setUndoMsg(r.message);
    } catch (e) {
      setUndoMsg(e instanceof Error ? e.message : String(e));
    }
    qc.invalidateQueries({ queryKey: ["feed"] });
  }

  return (
    <div data-testid="live-run" className={`overflow-hidden rounded-2xl border ${running ? "border-[#dbd7ff] bg-gradient-to-r from-primary-soft to-white" : "border-line bg-white"}`}>
      <button className="flex w-full items-center gap-3 px-3.5 py-3 text-left" onClick={() => setOpen(!open)}>
        <span className="relative grid h-9 w-9 flex-none place-items-center rounded-xl bg-primary-soft text-primary">
          <Icon name={running ? "spark" : run.state === "succeeded" ? "check" : "alert"} solid={running} className="h-4 w-4" />
          {running && <span className="live-dot is-live absolute -bottom-0.5 -right-0.5 border-2 border-white" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="eyebrow block">
            {running ? "Working now" : run.state === "succeeded" ? `Finished ${clock(run.finished_at ?? run.created_at)}` : run.state.replace("_", " ")}
            {" · "}{run.agent_name}
          </span>
          <span className="mt-0.5 block truncate text-[0.8rem] font-bold">
            {running ? (run.steps.at(-1)?.label ?? "Starting…") : run.headline}
          </span>
        </span>
        <span className="flex flex-none items-center gap-2 text-[0.62rem] font-semibold text-muted">
          <span>{elapsed(run)}</span>
          {(noAi || run.llm_calls > 0) && (
            <span className={`rounded-full px-2 py-0.5 ${noAi ? "bg-success-soft text-success" : "bg-canvas"}`}>
              {noAi ? "no AI" : `${run.llm_calls} AI call${run.llm_calls > 1 ? "s" : ""} · ${usd(run.cost_usd)}`}
            </span>
          )}
          <Icon name="chevron" className={`h-3.5 w-3.5 transition ${open ? "rotate-180" : ""}`} />
        </span>
      </button>
      {!compact && visible.length > 0 && (
        <ol className="space-y-1.5 border-t border-line/70 px-4 py-3">
          {visible.map((s, i) => {
            const current = running && i === visible.length - 1;
            return (
              <li key={s.idx} className="step-enter flex items-start gap-2 text-[0.74rem]">
                <span className={`mt-1 h-2 w-2 flex-none rounded-full ${current ? "live-dot is-live" : s.ok ? "bg-success" : "bg-warm"}`} />
                <span className={current ? "font-semibold text-ink" : s.ok ? "text-slate-600" : "text-[#9a5b25]"}>{s.label}</span>
                {open && <span className="ml-auto flex-none text-[0.6rem] text-muted">{s.latency_ms ? `${s.latency_ms} ms` : ""}</span>}
              </li>
            );
          })}
        </ol>
      )}
      {!running && run.undo_action_id && (
        <div className="flex items-center justify-between border-t border-line/70 px-4 py-2 text-[0.7rem]">
          <span className="text-muted">{undoMsg ?? "Done on its own — you can undo it."}</span>
          {!undoMsg && (
            <button className="btn-ghost px-2 py-1 text-[0.7rem]" onClick={undo}>
              <Icon name="undo" className="h-3.5 w-3.5" /> Undo
            </button>
          )}
        </div>
      )}
    </div>
  );
}
