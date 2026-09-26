import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../test/render";
import type { LiveRunT } from "../types";
import { LiveRun } from "./LiveRun";

const base: LiveRunT = {
  id: "r1", agent: "ingestion", agent_name: "Reading agent", mode: "deterministic", state: "succeeded",
  summary: "", headline: "Read your file → Entropy", goal: "", output: "", cost_usd: 0, llm_calls: 0,
  created_at: new Date().toISOString(), finished_at: new Date().toISOString(),
  steps: [{ idx: 0, kind: "tool", name: "check_legibility", label: "Page 1: text was clear — no AI needed", ok: true,
            latency_ms: 3, created_at: new Date().toISOString() }],
  undo_action_id: null,
};

describe("LiveRun", () => {
  it("shows the plain-language headline and a 'no AI' badge for a deterministic run", () => {
    renderWithProviders(<LiveRun run={base} defaultOpen />);
    expect(screen.getByText("Read your file → Entropy")).toBeInTheDocument();
    expect(screen.getByText("no AI")).toBeInTheDocument();
    expect(screen.getByText("Page 1: text was clear — no AI needed")).toBeInTheDocument();
  });

  it("never claims 'no AI' for a failed run", () => {
    renderWithProviders(<LiveRun run={{ ...base, state: "failed", headline: "Couldn't finish — see the steps" }} />);
    expect(screen.queryByText("no AI")).not.toBeInTheDocument();
  });
});
