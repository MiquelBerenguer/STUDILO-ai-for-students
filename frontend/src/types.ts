export interface Me {
  id: string;
  email: string | null;
  is_guest: boolean;
  display_name: string;
  journey_state: "onboarding" | "active";
  timezone: string;
  semester_start: string | null;
  semester_end: string | null;
  missed_after_hours: number;
}

export interface Course {
  id: string;
  name: string;
  color: string;
  syllabus: string;
  professor: string;
}

export interface Slot {
  id: string;
  course_id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  location: string;
}

export interface Exam {
  id: string;
  course_id: string;
  title: string;
  exam_date: string;
  scope_note: string;
}

export interface Assignment {
  id: string;
  course_id: string;
  title: string;
  due_date: string;
  done: boolean;
}

export type SessionState = "scheduled" | "awaiting_upload" | "uploaded" | "processed" | "missed";

export interface ClassSession {
  id: string;
  course_id: string;
  slot_id: string | null;
  session_date: string;
  starts_at: string | null;
  ends_at: string | null;
  state: SessionState;
  summary_md: string;
  topic_ids: string[];
  missed_reason: string;
}

export type UploadState =
  | "received" | "extracting" | "classifying" | "structuring" | "updating_memory" | "done" | "failed";

export interface Upload {
  id: string;
  course_id: string;
  class_session_id: string | null;
  kind: "notes" | "past_exam";
  filename: string;
  detected_type: string;
  size_bytes: number;
  state: UploadState;
  status_message: string;
  error: string;
  topic_id: string | null;
  job_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface IngestionLogRow {
  id: string;
  page: number | null;
  step: string;
  path_taken: string;
  reason: string;
  legibility_score: number | null;
  ocr_confidence: number | null;
  scores: Record<string, unknown>;
  model_used: string | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  created_at: string;
}

export interface UploadDetail extends Upload {
  extracted_md: string;
  log: IngestionLogRow[];
}

export interface Topic {
  id: string;
  course_id: string;
  parent_id: string | null;
  title: string;
  summary: string;
  position: number;
  section_count: number;
}

export interface SourceRef {
  upload_id: string;
  filename: string;
  created_at: string;
}

export interface Section {
  id: string;
  topic_id: string;
  position: number;
  heading: string;
  content_md: string;
  version: number;
  updated_at: string;
  sources: SourceRef[];
}

export interface TopicNote {
  topic: Topic;
  sections: Section[];
}

export interface SearchHit {
  section_id: string;
  topic_id: string;
  topic_title: string;
  heading: string;
  snippet: string;
  score: number;
}

export interface OpenQuestion {
  id: string;
  course_id: string;
  topic_id: string | null;
  text: string;
  status: "open" | "resolved";
  created_at: string;
}

export interface CourseMemory {
  course_id: string;
  topics_per_week: number;
  syllabus_position: string;
  pace_note: string;
  sessions: ClassSession[];
  open_questions: OpenQuestion[];
  dependencies: { topic_id: string; depends_on_id: string }[];
  missed_count: number;
}

export interface Question {
  id: string;
  position: number;
  topic_id: string | null;
  statement_md: string;
  points: number;
  cited_section_ids: string[];
  state: string;
  solution_md: string | null;
  rubric: { criterion: string; points: number }[] | null;
  verification: Record<string, unknown> | null;
}

export interface PracticeExam {
  id: string;
  number: number;
  title: string;
  duration_minutes: number;
  questions: Question[];
}

export interface GuideSection {
  id: string;
  topic_id: string | null;
  position: number;
  heading: string;
  content_md: string;
  cited_section_ids: string[];
}

export interface ExamPack {
  id: string;
  course_id: string;
  exam_id: string | null;
  version: number;
  trigger: string;
  state: "pending" | "building" | "ready" | "failed";
  error: string;
  notes_cutoff: string | null;
  built_at: string | null;
  job_id: string | null;
  created_at: string;
}

export interface ExamPackDetail extends ExamPack {
  study_guide: GuideSection[];
  practice_exams: PracticeExam[];
  citations: Record<string, { topic_id: string; topic_title: string; heading: string; course_id: string }>;
}

export interface Attempt {
  id: string;
  practice_exam_id: string;
  started_at: string;
  submitted_at: string | null;
  answers: Record<string, string>;
  self_scores: Record<string, number>;
}

export interface Job {
  id: string;
  type: string;
  state: "queued" | "running" | "succeeded" | "failed";
  progress: string;
  error: string;
  attempts: number;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Notification {
  id: string;
  kind: string;
  title: string;
  body: string;
  link: string;
  data: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface AgentRun {
  id: string;
  agent: string;
  mode: "llm" | "deterministic";
  prompt_version: string;
  task: string;
  job_id: string | null;
  state: string;
  goal: string;
  output: string;
  error: string;
  steps: number;
  llm_calls: number;
  cost_usd: number;
  created_at: string;
  finished_at: string | null;
}

export interface AgentStep {
  id: string;
  idx: number;
  kind: "llm" | "tool" | "decision";
  name: string;
  input: unknown;
  output: unknown;
  ok: boolean;
  latency_ms: number;
  created_at: string;
}

export interface LLMCall {
  id: string;
  agent_run_id: string | null;
  task: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  priced: boolean;
  latency_ms: number;
  ok: boolean;
  error: string;
  is_fallback: boolean;
  reason: string;
  created_at: string;
}

export interface ActivitySummary {
  total_cost_usd: number;
  llm_calls: number;
  llm_failed_calls: number;
  unpriced_calls: number;
  deterministic_steps: number;
  tool_steps: number;
  agent_runs: number;
  cost_by_task: Record<string, number>;
  calls_by_model: Record<string, number>;
  ingestion_paths: Record<string, number>;
}

export interface FeedItem {
  at: string;
  kind: string;
  text: string;
  link: string;
}

export interface ProviderStatus {
  name: string;
  key_env: string | null;
  configured: boolean;
  masked_key: string | null;
  base_url: string;
  used_by: string[];
}

export interface TaskMapping {
  task: string;
  provider: string;
  model: string;
  fallback: string[];
  priced: boolean;
}

// ------------------------------------------------------------------ Novi feed (UX.md §3–7)
export interface CardAction {
  id: string;
  label: string;
  type: "button" | "link" | "upload" | "date" | "text" | "credentials";
  primary?: boolean;
  href?: string;
  params?: Record<string, string>;
  course_choices?: { id: string; name: string }[];
}

export interface FeedCard {
  id: string;
  kind: string;
  title: string;
  body: string;
  link: string;
  data: Record<string, unknown>;
  actions: CardAction[];
  status: "open" | "done" | "dismissed";
  priority: number;
  action_id: string | null;
  undoable: boolean;
  course_id: string | null;
  created_at: string;
}

export interface RunStep {
  idx: number;
  kind: "llm" | "tool" | "decision";
  name: string;
  label: string;
  ok: boolean;
  latency_ms: number;
  created_at: string;
}

export interface LiveRunT {
  id: string;
  agent: string;
  agent_name: string;
  mode: string;
  state: "running" | "succeeded" | "failed" | "step_limit";
  summary: string;
  headline: string;
  goal: string;
  output: string;
  cost_usd: number;
  llm_calls: number;
  created_at: string;
  finished_at: string | null;
  steps: RunStep[];
  undo_action_id: string | null;
}

export interface NextItem {
  at: string;
  kind: "class_end" | "check" | "exam_pack";
  text: string;
}

export interface WeekItem {
  course_id: string;
  course: string;
  color: string;
  start: string;
  end: string;
  state: "upcoming" | "in_progress" | "ended" | "notes_in" | "missed";
}

export interface Feed {
  user_name: string;
  is_guest: boolean;
  status_line: string;
  counts: { needs_you: number; running: number; classes: number };
  cards: FeedCard[];
  live: LiveRunT[];
  since: LiveRunT[];
  next: NextItem[];
  week: WeekItem[];
  policy: { risk: "low" | "high"; action: string; mode: string }[];
  suggestions: string[];
}

export interface ActResult {
  message: string;
  card: FeedCard | null;
  job: Job | null;
}

export interface CommandResult {
  intent: string;
  method: "rules" | "llm" | "none";
  outcome: "job" | "proposal" | "navigate" | "needs" | "help";
  message: string;
  job_id: string | null;
  card_id: string | null;
  route: string | null;
  needs: string | null;
  choices: { id: string; label: string }[];
  parsed: Record<string, unknown>;
}

export interface Meta {
  brand: { name: string; tagline: string; slug: string };
  features: Record<string, boolean>;
}

// ------------------------------------------------------------------ onboarding (UX.md §8)
export interface ExtractedSlot {
  subject: string;
  weekday: number;
  start: string;
  end: string;
  room: string;
  professor: string;
  confidence: Record<"subject" | "time" | "room" | "professor", number>;
}

export interface Extraction {
  slots: ExtractedSlot[];
  exams: { subject: string; title: string; date: string }[];
  method: "ics" | "grid" | "text" | "vision" | "llm_text" | "none";
  confidence: number;
  warnings: string[];
  run_id: string | null;
}
