import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { get, post } from "../api";
import { useMe } from "../App";
import { CoursesEditor, ExamsEditor, ProfileEditor, ScheduleEditor, useCourses } from "../components/editors";
import { ErrorBox } from "../components/ui";
import type { Me, Slot } from "../types";
import { BRAND } from "../brand";

const STEPS = [
  { title: "Your subjects", hint: "What are you studying this semester?" },
  { title: "Weekly schedule", hint: `When are your classes? ${BRAND.name} asks for notes when each one ends.` },
  { title: "Semester dates", hint: `${BRAND.name} only follows classes inside the semester.` },
  { title: "Exam dates", hint: "Exam packs are built automatically 14, 7 and 3 days before. You can skip this." },
];

export default function Onboarding() {
  const [step, setStep] = useState(0);
  const { data: me } = useMe();
  const { data: courses = [] } = useCourses();
  const { data: slots = [] } = useQuery({ queryKey: ["slots"], queryFn: () => get<Slot[]>("/slots") });
  const qc = useQueryClient();
  const navigate = useNavigate();
  const finish = useMutation({
    mutationFn: () => post<Me>("/me/complete-onboarding"),
    onSuccess: (m) => { qc.setQueryData(["me"], m); navigate("/", { replace: true }); },
    onError: (e: Error) => {
      if (e.message.includes("subject")) setStep(0);
      else if (e.message.includes("schedule")) setStep(1);
      else if (e.message.includes("semester")) setStep(2);
    },
  });
  const canNext = [courses.length > 0, slots.length > 0, Boolean(me?.semester_start && me?.semester_end), true][step];

  return (
    <div className="mx-auto max-w-3xl p-4 md:p-10">
      <h1 className="text-2xl font-bold text-indigo-700">Welcome to {BRAND.name}</h1>
      <p className="text-sm text-slate-500">Four quick steps and {BRAND.name} starts following your courses.</p>
      <div className="mt-6 flex gap-2">
        {STEPS.map((s, i) => (
          <div key={s.title} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-indigo-600" : "bg-slate-200"}`} />
        ))}
      </div>
      <div className="card mt-6">
        <p className="text-xs font-semibold uppercase text-slate-400">Step {step + 1} of 4</p>
        <h2 className="text-lg font-semibold">{STEPS[step].title}</h2>
        <p className="mb-4 text-sm text-slate-500">{STEPS[step].hint}</p>
        {step === 0 && <CoursesEditor />}
        {step === 1 && <ScheduleEditor />}
        {step === 2 && me && <ProfileEditor me={me} />}
        {step === 3 && <ExamsEditor />}
        <ErrorBox error={finish.error} />
        <div className="mt-6 flex justify-between">
          <button className="btn-secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button>
          {step < 3 ? (
            <button className="btn-primary" disabled={!canNext} onClick={() => setStep(step + 1)}>Next</button>
          ) : (
            <button className="btn-primary" disabled={finish.isPending} onClick={() => finish.mutate()}>Finish setup</button>
          )}
        </div>
        {step === 2 && !canNext && <p className="mt-2 text-right text-xs text-slate-400">Save the semester dates to continue.</p>}
      </div>
    </div>
  );
}
