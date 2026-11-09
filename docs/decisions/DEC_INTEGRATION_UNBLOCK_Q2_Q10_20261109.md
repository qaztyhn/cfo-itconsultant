# Owner approvals — integration unblocking Q2–Q10 and manual merge control (2026-11-09)

**Status: OWNER APPROVED for Q2–Q10; Q1 is a manual-merge workflow instruction.** Source: direct owner confirmation in ITConsultant on 2026-11-09: “tôi cần nó chuyển sang cho phép merge. tôi sẽ tự bấm merge. các phần còn lại tôi đồng ý. Q1 tôi tự merge”. This accepts the nine specific recommendations Q2–Q10 previously presented in the project conversation, **not** a general authorization to change unrelated business rules, enable production integrations, or bypass review.

**Merge ownership (Q1):** AI agents/Integration Lead **must fix conflicts, review blockers, CI failures and dependencies so each safe PR can leave Draft and reach GitHub Ready for review / mergeable status**. The **Owner personally clicks Merge**. Agent may mark a PR *Ready for review* only when the described slice is truthful and independently safe; do **not** use Ready to hide an actual safety/contract blocker. Never auto-merge, bypass branch protection or forge approval. GitHub mergeability/required checks/reviewer approval are distinct from Draft status; an agent must verify each before telling Owner it is merge-ready. If an external integration is unverified, narrow the PR to a truthful fail-closed independent slice with tests and clear deferred scope rather than claiming the whole milestone is completed.

## DEC-INT-WMS-DEMO-20261109 — Q2: WMS mock reservation for staging/demo

- Approve an isolated **fake/synthetic WMS reservation adapter** for staging/demo testing of reserve/status/release, idempotency, ACK/timeout/retry, duplicate prevention, and immediate CFO refresh. It must be explicitly identified as simulated in API/UI/demo results; never claim stock guaranteed by a real WMS based on fake ACK.
- The real WMS port stays disabled until Dev 1/Dev 2 verify actual external API, authentication, credentials, SKU/unit mapping, authoritative reservation acknowledgment and recovery, and obtain separate deployment approval. This does **not** override DEC-WMS-RESERVE-SYNC's production gates or permit physical on-hand mutation.
- PR #163 may be reviewed as a disabled adapter slice, provided regression tests pass; neither owner approval nor a merge enables real writes.

## DEC-INT-TRANSFER-BOUNDARY-20261109 — Q3: CFO requests, WMS executes physical transfers

- CFO may **suggest/request** a warehouse transfer, with validated scope, reason and audit. **Only WMS executes physical outbound/inbound, receipt and stock-ledger changes**; CFO neither confirms a WMS physical issue/receipt on its own authority nor creates a stock-authoritative inbound from an internal click.
- Reconcile PR #127's existing `confirm-source`/`receive` implementation with this latest policy **before merge**: remove, disable or re-scope misleading CFO physical confirmation effects; preserve permitted review/audit functionality only. The earlier DEC-DEV1-D1-01/02 audit action meanings remain historical for any superseded CFO operation; do not invent physical stock authority.
- Post-`source_confirmed` reversal remains blocked absent separately approved WMS reversal contract; never infer transfer inclusion from a later batch timestamp or quantity delta.

## DEC-INT-AGREED-DATE-20261109 — Q4: Dispatcher applies verified customer-agreed date

- Store customer date-negotiation status and verifiable contact record first. A mere `agreed` entry **does not** change the committed date or approve a plan.
- **Only an authorized Dispatcher explicitly triggers “Apply agreed date”**, with a still-valid agreement record, version/concurrency guard, reason, and same-transaction audit. Update order's authorized date preference under a reviewed API/state transition; then request a **new planning run** and re-evaluate stock, official warehouse/driver shifts, driving-rest history, five gates and reservation. **No automatic approval, no unilateral change to already dispatched trip**.
- Dev 1/3 review the precise API DTO, state transition, source-of-truth boundary (POS remains unchanged unless separately authorized), and rollback/idempotency before implementation. UI must not expose a fake completed date change.

## DEC-INT-GPS-HISTORY-20261109 — Q5: case-specific historical GPS access

- Previously lawfully captured historical GPS (maximum seven-day retention per DEC-GPS-RET) may be read **only by an explicitly authorized privacy/compliance reviewer** assigned to the legitimate investigation/complaint case, with `case_id`, reason, market/trip scope and immutable read audit. Regular Dispatcher live-access rights do not automatically authorize finished-trip history.
- Reviewer identity/role/assignment and the case-level access API/schema require reviewed Dev 1/2 contract, RBAC and PostgreSQL tests. **No real-worker GPS collection or history read** without lawful basis, DPIA/notice/individual acknowledgment and legal/privacy sign-off. End trip/duty immediately revokes live collection/read, not authorized historical retention.
- This approval is a product/access policy, **not** evidence of legal compliance.

## DEC-INT-KPI-PERIOD-20261109 — Q6: KPI date range and explicit market

- KPI reporting defaults to a **30-day reporting window** and accepts at most a **366-day window**. Server validates inclusive/exclusive boundary semantics and interprets reporting cohorts in the **selected market IANA timezone** as already defined by KPI-2; document exact date parameters in Dev 1/3 DTO tests. No inferred cross-market merge.
- A System Admin working across multiple markets must **choose a market explicitly** before KPI read or baseline actions; no implicit all-market access or browser-derived market.
- Retain **10 published KPI keys**. `hard_constraint_violations` and `event_to_alert_latency_s_median` remain **`null`**, not estimated zero or invented formulas. Separate product review is required for real diagnostics; `CONFIG_CHANGED` baseline audit remains the existing documented action unless later changed.

## DEC-INT-PREP-ACTUAL-START-20261109 — Q7: nullable prep start

- `prep_window.start` is the actual persisted `START_PREP` event timestamp **or `null` before start**; do not synthesize it from planned shift/loading times, and never serialize a local naive timestamp. Values present are ISO 8601 offset-aware instants.
- If planned start is required in a future screen, it must have a **separate named field and reviewed DTO**, never overload `prep_window.start`.
- Align canonical M6 Prep Queue backend #159 and frontend #154/#160 validation/tests with this interpretation; missing official schedule still requires `schedule_verified=false`, verified available capacity zero.

## DEC-INT-SEED-GOLDEN-20261109 — Q8: golden tests are baseline, fix synthetic data

- Keep the currently documented/approved **golden scenario expected outcomes** as the acceptance baseline; adjust **synthetic** seed inputs/catalog, vehicle capacity, equipment semantics and official schedules as needed so inputs legitimately represent them.
- Do **not** change expected outcome, loosen engine safety rules, forge qualification, or flip test assertions just for a green build. If a golden case is mathematically impossible or conflicts with a higher-priority approved contract, produce quantitative evidence and a distinct reviewed spec/owner change request; leave case **BLOCKED**, not PASS.
- Synthetic 56-day driver history is not qualified real-driver compliance evidence. Do not auto-route old legacy orders after new SKU mappings.

## DEC-INT-CS-GET-PRIVACY-20261109 — Q9: protections for phone number in GET search

- Preserve owner-approved `GET /api/v1/orders?q=...` phone search; require HTTPS, proper market/CS authorization, adequate query specificity, throttle/abuse controls, **server/APM/access/analytics error-log redaction of raw query/phone**, and a browser `Referrer-Policy: no-referrer` for the search UI. Do not place raw phone in persistent UI navigation state, telemetry or server error responses.
- **Explicit residual risk:** a GET request URL can still expose the phone in browser history, reverse proxies, and debugging/network tools; log redaction and Referrer-Policy do not eliminate this. If stronger URL confidentiality is required later, a new **POST search API** needs an independent owner-reviewed contract. No such POST param/endpoint is approved here.
- Contract, middleware/proxy behavior, privacy E2E and effective rate-limit policy need Dev 1/2 review before exposure to real customer data.

## DEC-INT-D8-STAGING-EXEC-20261109 — Q10: D8 test environment and hosting

- Execute/stage the already owner-approved D8 schedule using **existing staging/test resources or controlled manual triggers** to prove job behavior and DST/locks/idempotency; do not enable production cron/workers or buy hosting on behalf of Owner.
- If a 24/7 worker, uptime SLA, paid platform, deployment region or real-data rollout is necessary, Dev 2 must present a scoped plan/cost and obtain **separate Owner approval**. Existing two `operational_review` slots remain 07:00 and 13:00 Europe/Stockholm; other proposed cadences are staging-only.
- Keep `attendance_gen` disabled without official roster contract and prohibit automated approval, unauthorized routing, real-customer DELAY notifications and real-employee GPS.

## Engineering handoff — turn Draft into reviewable, Owner-controlled merge

1. Integration Lead inventories **current** open PRs, verifies latest `main`, head SHAs, files, reviewer status, GitHub checks/branch protection and dependency DAG. Changes since this decision record must be rechecked, not inferred from an older PR list.
2. Prioritize **small independently safe/fail-closed slices** and resolve their conflicts, split duplicated/obsolete work, preserve regression tests. Do not mark a PR as feature-complete when it is only a disabled adapter/read UI or stub.
3. Update exact PR to current `main` or proper stacked base; avoid blind rebase/force push on shared agent branches; review migration ordering and contracts. Add negative/RBAC/concurrency/rollback cases and actual PostgreSQL/E2E evidence when needed.
4. Once independently reviewable and verified with latest-head CI, **mark Draft → Ready for review**, request another developer's review, and show Owner PR link, current SHA, green checks, any clearly deferred follow-up. `mergeable=true` does not itself guarantee GitHub merge policy approves the merge button.
5. **Owner alone chooses Merge**. No auto merge, no direct main writes, no bypass of required checks/reviews, no production enablement. If blocker persists, report `BLOCKED` plus exact next corrective task rather than flipping Draft prematurely.

**Out of scope:** ASM-004, ASM-008, unapproved GPS legal deployment, production D8 scheduling, paid hosting, live WMS API/writes, new KPI diagnostic formulas, and all other decisions not specifically Q2–Q10.
