import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

export function Markdown({ children, className = "" }: { children: string; className?: string }) {
  return (
    <div className={`markdown prose prose-slate max-w-none prose-headings:font-semibold ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

export function Card({ title, action, children, className = "" }: {
  title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold text-slate-800">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

const TONES: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
  indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  gray: "bg-slate-100 text-slate-600 ring-slate-200",
};

export function Badge({ tone = "gray", children }: { tone?: keyof typeof TONES | string; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${TONES[tone] ?? TONES.gray}`}>
      {children}
    </span>
  );
}

export const STATE_TONE: Record<string, string> = {
  done: "green", processed: "green", succeeded: "green", ready: "green", verified: "green",
  failed: "red", missed: "red", rejected: "red", step_limit: "red",
  awaiting_upload: "amber", queued: "gray", pending: "gray", scheduled: "gray",
  running: "blue", building: "blue", extracting: "blue", classifying: "blue", structuring: "blue",
  updating_memory: "blue", received: "gray", uploaded: "blue",
};

export function StateBadge({ state }: { state: string }) {
  return <Badge tone={STATE_TONE[state] ?? "gray"}>{state.replace(/_/g, " ")}</Badge>;
}

export function Spinner({ className = "" }: { className?: string }) {
  return <span className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent ${className}`} />;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center">
      <p className="font-medium text-slate-700">{title}</p>
      {children && <div className="mt-2 text-sm text-slate-500">{children}</div>}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{msg}</div>;
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="animate-pulse space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-4 rounded bg-slate-200" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function daysUntil(isoDate: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(`${isoDate}T00:00:00`);
  return Math.round((d.getTime() - today.getTime()) / 86400000);
}

export function fmtDate(iso: string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }) {
  return new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, opts);
}

export function fmtTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

export function usd(n: number) {
  return n === 0 ? "$0" : n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(3)}`;
}
