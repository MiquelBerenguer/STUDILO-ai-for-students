# View agents: how to start them

Four agents finish Novi in parallel, one per view (Ask Novi, Overview, Schedule, Courses). Each one works in its own worktree in
`/Users/miquel/Desktop/Personal/Studilo/novi-worktrees/<view>`. The rules they all follow are in
`AGENTS.md`; each agent's brief is in this folder.

## Before starting the agents
1. In the main checkout (`TUTOR-IA/tutor-ia-backend`), run `make dev`. This is the one real app
   (http://localhost:5173), with the one database and the background engine.
2. In Orca, open each worktree folder. Start one agent per folder and paste its prompt below.

## Prompts to paste (one per Orca worktree)

**ask-novi**
```
You are the Ask Novi agent. Read AGENTS.md, CLAUDE.md and docs/agents/ask-novi.md in this worktree, then follow the brief. Start by replying with your plan and wait for my go.
```

**overview**
```
You are the Overview agent. Read AGENTS.md, CLAUDE.md and docs/agents/overview.md in this worktree, then follow the brief. Start by replying with your plan and wait for my go.
```

**schedule**
```
You are the Schedule agent. Read AGENTS.md, CLAUDE.md and docs/agents/schedule.md in this worktree, then follow the brief. Start by replying with your plan and wait for my go.
```

**courses**
```
You are the Courses agent. Read AGENTS.md, CLAUDE.md and docs/agents/courses.md in this worktree, then follow the brief. Start by replying with your plan and wait for my go.
```

## When an agent finishes a piece
It commits on its branch and tells you what changed. To see a frontend change before merge, open its
preview URL (5174 ask-novi, 5175 overview, 5176 schedule, 5178 courses). Ask the integrator (the agent in the main checkout) to merge that view:
review → `make test` → merge into `master` → restart the main app. The other agents then run
`git merge master` to pick it up.
