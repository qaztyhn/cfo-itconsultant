/** Mapping API shapes from docs/06 §12.2 and backend mapping.py; feature-local until OpenAPI generated. */
import { apiGet, apiPost } from "../../api/client";

export interface Candidate {
  global_product_id: number;
  code: string;
  name: string;
  reason: string;
  score: number;
}
export interface MappingTask {
  id: number;
  market: string;
  local_sku: string;
  name: string | null;
  category: string | null;
  gtin: string | null;
  sale_unit: string | null;
  mapping_status: string | null;
  status: string;
  blocked_order_count: number;
  candidates: Candidate[];
  resolved_by: number | null;
  resolved_at: string | null;
  suggested_handling_group?: string | null;
}
export interface MappingPage<T> { items: T[]; page: number; page_size: number; total: number }
export interface LocalProduct {
  market: string; local_sku: string; name: string; category: string; gtin: string | null;
  sale_unit: string; units_to_base: string | number; unit_price: string | number;
  currency: string; global_product_id: number | null; mapping_status: string;
}
export interface NewGlobal {
  code: string; name: string; category: string; gtin?: string | null;
  base_unit: string; weight_kg: string; volume_m3: string;
  handling_group_code: string; base_units_per_prep_unit?: string | null; flags: string[];
}
export interface ConfirmRequest {
  units_to_base: string;
  global_product_id?: number;
  create_global?: NewGlobal;
}
export interface DecisionResponse {
  task_id: number; local_sku: string; global_product_id?: number;
  mapping_status: "confirmed" | "rejected";
}
export type TaskFilters = { status: string; q: string; market: string; page: number };
export type LocalFilters = { q: string; market: string; mapping_status: string; page: number };

export function listMappingTasks(filters: TaskFilters, signal?: AbortSignal) {
  return apiGet<MappingPage<MappingTask>>("/mapping/tasks", {
    status: filters.status, q: filters.q, market: filters.market,
    page: filters.page, page_size: 20,
  }, signal);
}
export function loadMappingTask(id: number, signal?: AbortSignal) {
  return apiGet<MappingTask>(`/mapping/tasks/${id}`, undefined, signal);
}
export function listLocalProducts(filters: LocalFilters, signal?: AbortSignal) {
  return apiGet<MappingPage<LocalProduct>>("/products/local", {
    q: filters.q, market: filters.market, mapping_status: filters.mapping_status,
    page: filters.page, page_size: 20,
  }, signal);
}
export function confirmMapping(id: number, request: ConfirmRequest) {
  return apiPost<DecisionResponse>(`/mapping/tasks/${id}/confirm`, request);
}
export function rejectMapping(id: number, reason_text: string) {
  return apiPost<DecisionResponse>(`/mapping/tasks/${id}/reject`, { reason_text });
}

export function validPositiveDecimal(value: string): boolean {
  return /^\d+(?:\.\d+)?$/.test(value.trim()) && Number.isFinite(Number(value)) && Number(value) > 0;
}
export function validateGlobal(product: NewGlobal): string[] {
  const errors: string[] = [];
  if (![product.code, product.name, product.category, product.base_unit].every(v => v.trim().length > 0)) {
    errors.push("Code, name, category and base unit are required.");
  }
  if (!/^N[1-6]$/.test(product.handling_group_code)) errors.push("Choose a handling group N1–N6.");
  if (!validPositiveDecimal(product.weight_kg) || !validPositiveDecimal(product.volume_m3)) {
    errors.push("Positive weight and volume are required.");
  }
  // For the line-based group, server still checks the actual preparation-unit rule.
  if (!validPositiveDecimal(product.base_units_per_prep_unit ?? "")) {
    errors.push("Specify a positive base-units-per-preparation-unit factor.");
  }
  if (product.handling_group_code === "N6" && product.flags.includes("FRAGILE")) {
    errors.push("N6 may not carry the FRAGILE flag.");
  }
  return errors;
}
export function candidateEvidence(candidate: Candidate): string {
  if (candidate.reason === "gtin") return "GTIN match";
  if (candidate.reason === "name_sim") return "Name/category similarity (pg_trgm)";
  return `Rule evidence: ${candidate.reason}`;
}
