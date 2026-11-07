---
name: cfo-dev3-frontend
description: Implement or review CFO IT Consultant Dev 3 React, TypeScript, Tailwind, UI/UX, OpenAPI client, MSW mocks, POS UI and driver PWA features. Do not use for database migrations, backend planning algorithms or infrastructure ownership.
---

# CFO Dev 3 — Frontend, POS UI and driver PWA

Use for Dev 3's owned screens and end-user flows. This skill supplements, never replaces, the project contracts.

## Source of truth

1. Read `AGENTS.md` and **all** of `docs/09_AI_Coding_Rules.md` before coding; recheck its invariants and definition of done before PR.
2. Read `docs/10_Team_Assignment.md` for exact ownership, `docs/08_Development_Plan.md` for active milestone, the relevant US/AC in `docs/02_User_Stories_and_Acceptance_Criteria.md` and business rules in `docs/01_PRD.md`.
3. For screens, read `docs/03_UI_UX_Specification.md` (its corrections override the design reference), `docs/07_User_Flows.md`, `docs/06_API_Specification.md` and affected permission/location matrices.

## Owned modules

- `frontend/` and `source_system/pos_ui/`.
- Components, pages, role-aware routing, design tokens, React Query hooks, OpenAPI-generated API client, MSW fixtures, visual tests and driver PWA.
- Do not change `backend/app/`, migrations, source adapters, jobs, Docker or CI unilaterally.

## Mandatory implementation workflow

1. Check `git status --short`, branch, existing components, current milestone and API dependency status. Preserve other agents' worktrees.
2. Give a short plan listing screens/components, exact US/AC/BR, permission states, API methods, mocks and tests. Split PRs when logic changes exceed roughly 400 lines.
3. Implement against the exact `06` API schema. Use generated TypeScript/OpenAPI client rather than hand-authored API contracts. If the real endpoint is missing, implement documented MSW mocks and identify the integration dependency; never invent a backend behavior.
4. Use TypeScript strict, existing React/Vite/Tailwind conventions, reusable components and documented design tokens; no hard-coded UI colors outside tokens. Respect the textual UI specification when it differs from screenshots.
5. Test authorized and unauthorized roles, location scoping, disabled actions and data masking. Hiding a button is **not** a substitute for backend authorization. Never expose GPS to non-dispatcher roles or PII in console logs.
6. Include loading, empty, error (correlation ID + retry), success and conflict states for data screens. Ensure keyboard navigation, accessible form labels, AA contrast, textual risk indicators and i18n.
7. For driver PWA, respect permission-before-location, offline IndexedDB queue, event `occurred_at` and idempotency keys; verify duplicate resend prevention and appropriate privacy messaging.
8. Run targeted UI tests and `python tools/harness.py frontend`, then `python tools/harness.py verify` from repo root (PowerShell: `py -3.12 tools/harness.py ...`). Do not claim unexecuted tests passed.
9. Report screens finished, exact ACs, screenshots or behavior notes, mocks versus real endpoints, verification output and integration blockers. Create a reviewed PR when requested; never auto-merge.

## Coordination and stop conditions

- Ask Dev 1/2 to publish backend/source contracts instead of editing their services.
- No automatic approvals, delivery-date changes, or DELAY notifications in UI workflows. Keep dispatcher as final decision-maker.
- Do not add WebSocket, expensive external UI services or unrelated dependencies without approval.
