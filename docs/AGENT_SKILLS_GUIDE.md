# CFO IT Consultant — Agent Skills (Dev 1 / Dev 2 / Dev 3)

Repository-local skills for **Codex** and **Claude Code**. These files provide repeatable workflows; they do not alter application runtime and do not grant GitHub, Supabase, or production permissions.

## Installed skills

| Developer | Skill | Ownership |
| --- | --- | --- |
| Dev 1 | `cfo-dev1-backend` | `backend/alembic`, core/domain/engine/audit, owned backend APIs/services |
| Dev 2 | `cfo-dev2-integration` | `source_system` backend, adapters, providers, jobs, seeds, tools, Docker/CI |
| Dev 3 | `cfo-dev3-frontend` | `frontend`, `source_system/pos_ui`, driver PWA and generated API client |

The canonical **project specifications**, not the skills, remain `AGENTS.md` and `docs/09_AI_Coding_Rules.md`, plus `docs/05`, `docs/06` and the other versioned docs in their prescribed precedence. Always check current milestones and ownership in `docs/08_Development_Plan.md` and `docs/10_Team_Assignment.md`.

## Where agents discover skills

- Codex: `.agents/skills/<name>/SKILL.md`
- Claude Code: `.claude/skills/<name>/SKILL.md`

Both directories contain the same skill bodies so that either tool discovers them independently. When modifying a skill, update **both copies in the same PR**.

## Run from your own worktree

1. Pull the branch containing these skills (after this PR has been merged, `git pull --ff-only` on your worktree's base branch, or merge/rebase the updated base into your feature branch safely).
2. Launch Codex/Claude from the **CFO repo or its worktree**; use an isolated working branch per developer. Do not point different agents at a shared dirty working tree.
3. In the agent chat, request the skill by name and a *bounded* task with a milestone, issue or US/AC reference.
4. Let the agent inspect status/specs and implement. Review its tests and PR before merging.

### Example prompts in Codex chat

Dev 1:

```text
Use $cfo-dev1-backend. Inspect the current milestone, my branch, and the next unblocked backend issue assigned to Dev 1. Implement one reviewable slice, add AC tests, run relevant harness checks and open a PR only if you have push access. Do not merge.
```

Dev 2:

```text
Use $cfo-dev2-integration. Inspect the current milestone and dependencies. Complete one assigned integration/seed/infra slice with contract tests, run harness verification, and open a PR if permitted. Do not merge or reset databases.
```

Dev 3:

```text
Use $cfo-dev3-frontend. Implement the next assigned UI story from the current milestone using the exact UI and OpenAPI specs, with MSW mocks if the API is not ready. Run frontend checks and open a PR if permitted. Do not merge.
```

### Example prompts in Claude Code chat

Use `/cfo-dev1-backend`, `/cfo-dev2-integration`, or `/cfo-dev3-frontend` followed by the task and acceptance criteria.

## Verification gates

From the repo root:

```powershell
py -3.12 tools/harness.py doctor
py -3.12 tools/harness.py verify
```

To run on macOS/Linux, substitute `python` for `py -3.12`. `verify` does not install tools or start Docker for you; consult `docs/HARNESS_SETUP.md`. Only report checks that actually ran. The harness is project-owned; these skills do **not** install external third-party skills.

## Team safety

- One task/PR at a time per agent; branches/worktrees isolated. Review with the required code owner per `docs/10_Team_Assignment.md`.
- No silent changes to schema (`05`), API (`06`), security rules, sensitive business decisions, or source/production data.
- No secrets or private customer data in code, seeds, logs or PR descriptions.
- Skills automate the workflow description, not permission to run forever or skip human review.
