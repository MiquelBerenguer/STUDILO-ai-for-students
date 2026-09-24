# Changelog

## Phase 0 — Audit and cleanup (2026-09-24)

### Root cause of issue #8, "status endpoint always returns PROCESSING" (recorded before the fix)
There are two independent causes, and fixing either one alone would not have been enough:

1. **Hardcoded value.** `src/services/learning/api/routes.py`, `check_exam_status()`, returned the
   literal `{"status": "PROCESSING", "download_url": None}` for any `task_id`, without reading anything.
2. **No real job data existed to read.** `request_exam_generation()` published a RabbitMQ message and
   returned `QUEUED` without inserting any row. `exam_worker.py` wrote the PDF to MinIO, then only
   logged success. On failure it logged and swallowed the exception. No component ever recorded
   `completed`/`failed`, and the only durable trace (the MinIO object) had no link to the `task_id`.
   The PDF pipeline had the same defect: the processor wrote a Redis status the active worker never
   updated, on a queue the worker did not consume.

Fix (Phase 0/M4): job state is a `jobs` row written by the orchestrator in the same process that runs
the work. The state machine is `queued → running → succeeded | failed`, and domain entities
(uploads, exam packs) have their own explicit state machines. Status endpoints read those rows.
Tests assert the state progression.

### Other changes
- Confirmed and extended the audit (`PLAN.md` §1, findings A1–A7).
- Pre-existing uncommitted changes preserved in `git stash@{0}`. Work continues on branch `studilo-v1`.
