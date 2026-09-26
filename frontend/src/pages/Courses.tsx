// Courses (secondary view): drill into a course's notes, memory and sources.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { get, post } from "../api";
import { Icon } from "../components/icons";
import { daysUntil, Empty, fmtDate } from "../components/ui";
import type { Course, Exam } from "../types";

export default function Courses() {
  const { data: courses = [], isLoading } = useQuery({ queryKey: ["courses"], queryFn: () => get<Course[]>("/courses") });
  const { data: exams = [] } = useQuery({ queryKey: ["exams"], queryFn: () => get<Exam[]>("/exams") });
  if (!isLoading && courses.length === 0) return <Empty title="No courses yet">Import your timetable from Schedule.</Empty>;
  return (
    <div className="card max-w-3xl">
      <div className="section-title">Courses</div>
      <p className="text-[0.7rem] text-muted">{courses.length} active this semester</p>
      <ul className="mt-3">
        {courses.map((c) => {
          const exam = exams.filter((e) => e.course_id === c.id && daysUntil(e.exam_date) >= 0)
            .sort((a, b) => a.exam_date.localeCompare(b.exam_date))[0];
          return (
            <li key={c.id} className="border-t border-line first:border-t-0">
              <Link to={`/subjects/${c.id}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                <span className="grid h-9 w-9 place-items-center rounded-xl" style={{ background: `${c.color}1f`, color: c.color }}>
                  <Icon name="book" className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[0.8rem] font-bold">{c.name}</span>
                  <span className="block text-[0.68rem] text-muted">{c.professor ? `Prof. ${c.professor}` : "Professor not set"}</span>
                </span>
                <span className="text-right text-[0.66rem] text-muted">
                  {exam ? <>{exam.title}<br /><b className="text-primary">{fmtDate(exam.exam_date)} · {daysUntil(exam.exam_date)}d</b></> : "No exam date yet"}
                </span>
                <Icon name="arrow" className="h-4 w-4 text-muted" />
              </Link>
              {!c.syllabus.trim() && <GuideFetch courseId={c.id} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Empty syllabus → fetch it from the public UPC course guide by subject code (no AI, upc.edu only). */
function GuideFetch({ courseId }: { courseId: string }) {
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const qc = useQueryClient();
  return (
    <form className="mb-3 ml-12 flex flex-wrap items-center gap-2 text-[0.7rem]" onSubmit={async (e) => {
      e.preventDefault();
      try {
        const r = await post<{ message: string }>(`/courses/${courseId}/guide`, { code });
        setMsg(r.message);
        qc.invalidateQueries({ queryKey: ["courses"] });
      } catch (err) {
        setMsg(err instanceof Error ? err.message : String(err));
      }
    }}>
      <span className="text-muted">No syllabus yet —</span>
      <input className="input w-40 py-1 text-[0.7rem]" placeholder="UPC subject code" value={code}
        onChange={(e) => setCode(e.target.value)} pattern="[0-9]{5,6}" required aria-label="Subject code" />
      <button className="btn-secondary px-2.5 py-1">Fetch from course guide</button>
      {msg && <span className="w-full text-muted">{msg}</span>}
    </form>
  );
}
