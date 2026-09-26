// Onboarding in 3 steps (UX.md §8): drop timetable → confirm week → Novi feed. No registration wall.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { post } from "../api";
import { BRAND } from "../brand";
import { BrandMark } from "../components/icons";
import { TimetableCapture, WeekPreview } from "../components/Timetable";
import type { ExtractedSlot, Extraction, Me } from "../types";

export default function Onboarding({ me }: { me: Me | null }) {
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [slots, setSlots] = useState<ExtractedSlot[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [guestReady, setGuestReady] = useState(!!me);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const step = extraction ? 2 : 1;

  async function ensureGuest() {
    if (guestReady) return;
    await post("/auth/guest", { timezone: Intl.DateTimeFormat().resolvedOptions().timeZone });
    setGuestReady(true);
  }

  async function confirm() {
    const valid = slots.filter((s) => s.subject.trim() && s.start < s.end);
    if (!valid.length) return setError("Keep at least one class with a subject and a time.");
    setBusy(true);
    setError(null);
    try {
      await post("/onboarding/confirm", { slots: valid, exams: extraction?.exams ?? [] });
      await qc.invalidateQueries({ queryKey: ["me"] });
      navigate("/?welcome=1", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-canvas px-4 py-8">
      <div className={`mx-auto ${step === 2 ? "max-w-5xl" : "max-w-xl"}`}>
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BrandMark />
            <span className="text-[1.3rem] font-bold tracking-[-0.04em]">{BRAND.name}</span>
          </div>
          {!me && <Link to="/login" className="text-[0.76rem] font-semibold text-primary">I already have an account</Link>}
        </div>
        <Steps step={step} />
        <div className="card mt-4 p-6">
          {step === 1 ? (
            <>
              <h1 className="title-xl">Drop your timetable</h1>
              <p className="mb-5 mt-1 text-[0.82rem] text-muted">
                {BRAND.tagline} Give me the timetable you already have and I'll set everything up — no forms.
              </p>
              <TimetableCapture beforeExtract={ensureGuest} onExtracted={(x) => { setExtraction(x); setSlots(x.slots); }} />
            </>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h1 className="title-xl">Here's your week — looks right?</h1>
                  <p className="mt-1 text-[0.82rem] text-muted">Tap anything to fix it. Exam dates and the rest I'll ask when they matter.</p>
                </div>
                <div className="flex gap-2">
                  <button className="btn-ghost" onClick={() => { setExtraction(null); setSlots([]); }}>Try another</button>
                  <button data-testid="confirm-schedule" className="btn-primary px-5 py-2.5" disabled={busy} onClick={confirm}>
                    {busy ? "Setting up…" : "Looks right"}
                  </button>
                </div>
              </div>
              {extraction && <WeekPreview extraction={extraction} slots={slots} onChange={setSlots} />}
              {error && <p className="mt-3 text-[0.76rem] text-red-600">{error}</p>}
            </>
          )}
        </div>
        <p className="mt-4 text-center text-[0.68rem] text-muted">
          No account needed to start — save it later with an email. Files are processed on this machine; AI is used only when a picture is hard to read.
        </p>
      </div>
    </div>
  );
}

function Steps({ step }: { step: number }) {
  const items = ["Drop your timetable", "Confirm your week", "You're set"];
  return (
    <ol className="flex items-center gap-2 text-[0.68rem] font-bold">
      {items.map((label, i) => (
        <li key={label} className="flex flex-1 items-center gap-2">
          <span className={`grid h-6 w-6 flex-none place-items-center rounded-full ${i + 1 < step ? "bg-success text-white" : i + 1 === step ? "bg-primary text-white" : "bg-line text-muted"}`}>
            {i + 1 < step ? "✓" : i + 1}
          </span>
          <span className={`truncate ${i + 1 === step ? "text-ink" : "text-muted"}`}>{label}</span>
          {i < items.length - 1 && <span className="h-px flex-1 bg-line" />}
        </li>
      ))}
    </ol>
  );
}
