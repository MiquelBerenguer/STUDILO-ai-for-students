import { useQuery, useQueryClient } from "@tanstack/react-query";

import { get } from "./api";
import type { Feed, Job, LiveRunT, Meta } from "./types";

/** The Novi feed. Polls fast (1 s) while an agent is running so steps stream in, slower otherwise. */
export function useFeed() {
  return useQuery({
    queryKey: ["feed"],
    queryFn: () => get<Feed>("/feed"),
    refetchInterval: (q) => ((q.state.data?.counts.running ?? 0) > 0 ? 1000 : 5000),
  });
}

/** Runs of one job (an upload, a command request): poll every second until none is running. */
export function useJobRuns(jobId: string | null | undefined) {
  return useQuery({
    queryKey: ["runs", "job", jobId],
    queryFn: () => get<LiveRunT[]>(`/runs/live?job_id=${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const runs = q.state.data;
      return !runs || runs.length === 0 || runs.some((r) => r.state === "running") ? 1000 : false;
    },
  });
}

export function useJob(jobId: string | null | undefined) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: async () => {
      const job = await get<Job>(`/jobs/${jobId}`);
      if (job.state === "succeeded" || job.state === "failed") qc.invalidateQueries({ queryKey: ["feed"] });
      return job;
    },
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data && ["succeeded", "failed"].includes(q.state.data.state) ? false : 1000),
  });
}

/** Brand + feature flags (config/features.json). Stubs render only when their flag is on (UX.md §10). */
export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: () => get<Meta>("/meta"), staleTime: Infinity });
}

export function useFeature(name: string): boolean {
  return useMeta().data?.features[name] ?? false;
}

export function relTime(iso: string, now = Date.now()): string {
  const diff = Math.round((new Date(iso).getTime() - now) / 60000);
  const abs = Math.abs(diff);
  const fmt = abs < 1 ? "just now" : abs < 60 ? `${abs} min` : abs < 1440 ? `${Math.round(abs / 60)} h`
    : `${Math.round(abs / 1440)} d`;
  if (abs < 1) return fmt;
  return diff < 0 ? `${fmt} ago` : `in ${fmt}`;
}

export function clock(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return sameDay ? time : `${d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })} ${time}`;
}
