# Dev 3 handoff: complete reverse SKU evidence for Product Mapping

The current `GET /products/local` returns a filtered, paginated list with `local_sku`, `global_product_id`, and `mapping_status`. The UI can show only associations in the loaded page. It cannot assert that all source SKUs for a global product have been found, and it cannot select a WMS-native reservation SKU. No new endpoint or response DTO is introduced in PR #158.

Dev 1/2 should review an authenticated, market-scoped read contract that can answer, for a given global product and warehouse, whether the original order-line SKU and every relevant confirmed mapping are known. The contract needs server-authored completeness/pagination evidence, mapping version/effectivity, original POS SKU, separately verified WMS-native SKU where different, fixed stock unit/conversion, warehouse availability and source batch version. A result with ambiguity or missing evidence must not authorize a WMS reserve request. Define the exact route, permission matrix, DTO and error codes in `docs/06` before UI integration.

Acceptance cases: two local SKUs map to one global product; POS and WMS SKUs differ; results cross pages or markets; mapping changes after order capture; warehouse has only one of the SKUs; conversion or independence evidence is missing. The backend remains responsible for selecting and validating a specific order-line/warehouse/SKU allocation. The Product Mapping UI must never infer that choice from a paginated catalogue page.

Sources reviewed: `DEC_WMS_REVERSE_SKU_FOR_RESERVATIONS_20261109`, `DEC_WMS_RESERVE_SYNC_20261109`, `docs/06` §12 and `docs/ASSUMPTIONS.md`. Assumptions: reviewed — none added.
