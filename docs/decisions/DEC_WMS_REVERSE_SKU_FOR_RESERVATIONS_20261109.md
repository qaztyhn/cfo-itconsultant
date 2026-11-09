# DEC-WMS-REVERSE-SKU-20261109 — Reverse mapping for prospective CFO → WMS reservation calls

**Status: OWNER-APPROVED CONDITIONAL REQUIREMENT (2026-11-09).** The owner specified: “cái này nếu mà từ cfo về thì phải ánh xạ ngược lại mã sản phẩm cũ”. The rule applies **if** any CFO-to-WMS reserve/release request is authorized. **It does not, by itself, approve WMS writes or verify an endpoint**; `DEC-WMS-READONLY-20261109` remains the active integration boundary until the owner separately approves a narrow write exception.

## Business rule

- CFO plans using **global product IDs/codes**, but the WMS reservation interface must receive **the correct original WMS-recognized product SKU** in the market and warehouse where stock is allocated. Never send a CFO `global_product_id` or `global_code` as if it were the legacy WMS SKU. The original Source/POS `local_sku` must be retained with order line provenance. **Do not assume POS `local_sku` equals WMS SKU** without verifying the actual WMS contract; if different, use an explicitly approved mapping to the WMS-native SKU.
- Validate the **confirmed** mapping, market, warehouse, SKU availability, effective product/mapping version, request order line identity and stock-unit conversion before construction. In existing model `order_line.local_sku` and `global_product_id` are distinct and `qty_base` derives from `qty_sale × units_to_base`; WMS stock quantities use that SKU's fixed published stock unit under `DEC-SRC-Q10-SKU-001`.
- An inverse `global_product_id → local_sku` is **not necessarily a function**: multiple original SKUs can map to one global product. **Never choose the first match or invent a stock pool.** Preserve/order-line-specific SKU if compatible and actually assigned to the selected WMS warehouse, otherwise require a uniquely verified warehouse+market source SKU allocation. Distinct WMS SKUs are distinct inventory rows unless independently reviewed evidence authorizes any aggregation. If a reservation spans multiple original SKUs, represent explicit quantities per source SKU, not a single guessed alias.
- Resolve quantities in the **WMS SKU stock unit** using a verified conversion, exact decimal arithmetic, and integer/precision rules from the actual WMS contract. Reject unsupported fractional quantities, ambiguous conversions, changed/expired mappings, missing original SKU, missing WMS warehouse identity, unapproved scope and stale stock context. No silent rounding.
- Keep request/response provenance: `market`, WMS warehouse identifier, CFO order/line, original POS SKU, resolved WMS SKU, approved mapping version, WMS stock unit, requested quantity, source snapshot/version and idempotency/external correlation ID. The WMS reservation acknowledgement must identify exactly the accepted SKU/warehouse/quantity and revision. Mismatch or uncertain/timeout status => fail closed and reconcile through an idempotent status lookup, never blindly retry or claim success.
- Prevent double-accounting: WMS reserves reduce **available** but not physical **on_hand**; after WMS acknowledges the CFO-originated reservation, CFO cannot subtract that same reservation again from WMS available. Physical issue is WMS-owned. CFO temporary planning holds and committed reservation lifecycle require an explicit ownership and inclusion contract before any outbound WMS operation.

## Scope and non-approval

This is a **required mapping invariant for a proposed integration**, not authorization to write to legacy WMS or edit POS. Dev 1/Dev 2 should document the exact WMS reservation API, what SKU identifiers it accepts and its quantity unit, design a safe reverse-lookup/resolver with effective mappings and warehouse scoping, and obtain explicit approval of narrowly scoped `reserve/status/release` writes before implementation.

## Acceptance scenarios

1. One confirmed source SKU maps to one global product → the original WMS SKU and correctly converted stock-unit quantity are submitted.
2. Two local SKUs map to one global product → no arbitrary inverse mapping or pooled quantity; use verified original line/warehouse allocation or block.
3. POS source SKU differs from WMS SKU → only an explicitly confirmed POS↔WMS SKU relation is accepted; otherwise block.
4. Unmapped/rejected/changed/expired mapping or wrong market/warehouse → no outbound request.
5. Invalid unit, fractional stock-unit amount, missing batch, stale data, insufficient stock or ambiguous allocation → fail closed.
6. WMS accepts only part of the requested lines, returns mismatch, times out or duplicates a request → do not mark CFO stock guaranteed, use reviewed idempotent retry/lookup and compensating release when appropriate.

Existing scope/routing rules still apply: only 100%-confirmed SKU orders enter CFO; no physical_stock_pool alias inference or CFO writes to WMS without a separate owner-approved contract.

## Subsequent owner confirmation of reserve flow

The reservation flow itself has now been **approved as business intent** in [DEC-WMS-RESERVE-SYNC-20261109](DEC_WMS_RESERVE_SYNC_20261109.md): CFO checks WMS data, authorized user confirms, WMS reserves/lowers available and CFO immediately refreshes its stock. The reverse-SKU guard above is mandatory in this future request. This still does not constitute verified WMS API or deployment security authorization.
