# BE-03 — CS Contact Log persistence service (independent incremental slice)

**Date:** 2026-11-09. **Status:** service-only, not E2E. The approved
`docs/06_API_Specification.md` §11 contract defines the existing
`POST/GET /orders/{id}/contact-logs` endpoints. This PR **does not**
activate those endpoints: their stubs live in `backend/app/api/v1/orders.py`,
currently concurrently edited by CS DTO PR #189.

The new `customer_contact_service.create(session, actor, order_id, channel,
reason_code, note)` writes `ops.customer_contact_log`, binds the authenticated
CS actor/employee and trusted timestamp, checks market and order ownership and
inserts a typed, **PII-free** audit in the same caller transaction. No user
input may override the actor/time or audit snapshot. Transaction rollback
removes both log and audit. It never sends a customer notification.

**Owner approved Option A on 2026-11-09:** `list_logs` checks role and
market, orders by timestamp/id and paginates. CS-only readers receive `note`;
Dispatcher-only readers receive `id`, `order_id`, `channel`, `reason_code`,
`contacted_at` with **no `note` key** (not even null). Permission is based on
authenticated backend roles, not a client filter; audit/logs never include notes.

## Pending API integration (next independently reviewed PR)
- After PR #189 merges, replace the existing two stubs in `orders.py` with
  typed input/output DTOs, dependency-injected `AuthUser`/`DbSession`,
  pagination and a caller-owned transaction invoking this service.
- Use the existing names/URLs from §11; do not invent a new endpoint or accept
  client-provided `employee_id`, `contacted_at`, `customer_id` or market.
- Add real PostgreSQL API RBAC, cross-market and error-response tests,
  and verify generated OpenAPI + frontend projection in a distinct review.
- Owner approved CS-only note visibility. Review free-text note retention
  with Dev 2/privacy under D5; never echo note in logs, audit, or unapproved DTOs.

**Tests:** real PostgreSQL service tests cover allowed CS persistence, reader
roles, cross-market concealment, negative RBAC, invalid codes, pagination,
audit's no-PII shape and atomic rollback. Exact-head CI must pass. No schema
migration required: `ops.customer_contact_log` exists. The new typed audit
action is `CUSTOMER_CONTACT_RECORDED` (audit-only, not a business transition).
