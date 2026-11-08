/** Defensive projection of untrusted integration API payloads. No raw PII leaves this module. */
import type {
  FeedEntity,
  OverviewResponse,
  OverviewSource,
  RejectResponse,
  RunStatus,
  SyncRunResponse,
} from "./contracts";
import { FEEDS } from "./contracts";

export type DisplayStatus = RunStatus | "unknown" | "blocked";
export interface SourceView {
  entity: FeedEntity;
  title: string;
  source: string;
  status: DisplayStatus;
  rows: number | null;
  rejected: number | null;
  unmapped: number | null;
  lastRunAt: string | null;
  dataAsOf: string | null;
  latestStatus: DisplayStatus;
  lastSuccessfulAt: string | null;
  /** API may return a configured interval, but this is NOT proof that a worker is running. */
  reportedIntervalMin: number | null;
}
export interface RunView {
  id: number;
  entity: FeedEntity;
  status: DisplayStatus;
  startedAt: string | null;
  finishedAt: string | null;
  dataAsOf: string | null;
  checkpointFrom: string | null;
  checkpointTo: string | null;
  kind: "api" | "csv" | null;
  rowsIn: number | null;
  rowsOk: number | null;
  rowsRejected: number | null;
}
export interface RejectView {
  id: number | null;
  reasonCode: string;
  detail: string;
}
export interface MatrixView {
  pairs: number | null;
  fallbackPairs: number | null;
  fetchedAt: string | null;
  provider: string | null;
}
export interface SchedulerView {
  lastTickAt: string | null;
  lastTickStatus: string | null;
  reportedIntervalMin: number | null;
  jobs: string[];
}

const ENTITIES: ReadonlySet<string> = new Set(FEEDS.map((feed) => feed.entity));
const STATUSES: ReadonlySet<string> = new Set(["ok", "partial", "failed", "running"]);
const REASONS: Record<string, string> = {
  BAD_QTY: "Quantity failed source validation.",
  UNKNOWN_WAREHOUSE: "Warehouse identifier was not recognised.",
  BAD_DATE: "Date did not pass validation.",
  MISSING_COORDS: "Required geographic coordinates were missing.",
  UNKNOWN_SKU: "SKU is not in the source catalogue. Review product mapping.",
};

export function safeCount(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function safeStatus(value: unknown): DisplayStatus {
  return typeof value === "string" && STATUSES.has(value) ? (value as RunStatus) : "unknown";
}

/** UTC presentation prevents browser locale offset from silently changing source audit dates. */
export function timestamp(value: unknown): string | null {
  if (typeof value !== "string" || !/\d{4}-\d\d-\d\dT\d\d:\d\d/.test(value)) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && /(?:Z|[+-]\d\d:\d\d)$/.test(value)
    ? date.toISOString().slice(0, 16).replace("T", " ") + " UTC"
    : null;
}

export function readableNumber(value: number | null): string {
  return value === null ? "Not reported" : value.toLocaleString("en-US");
}

export function normalizeRuns(input: unknown): RunView[] {
  if (!input || typeof input !== "object") return [];
  const raw = input as { items?: unknown };
  if (!Array.isArray(raw.items)) return [];
  return (raw.items as SyncRunResponse[]).flatMap((item) => {
    if (!item || !Number.isSafeInteger(item.id) || (item.id as number) < 1 || !ENTITIES.has(String(item.entity))) {
      return [];
    }
    return [{
      id: item.id as number,
      entity: item.entity as FeedEntity,
      status: safeStatus(item.status),
      startedAt: timestamp(item.started_at),
      finishedAt: timestamp(item.finished_at),
      dataAsOf: timestamp(item.data_as_of),
      checkpointFrom: timestamp(item.checkpoint_from),
      checkpointTo: timestamp(item.checkpoint_to),
      kind: item.kind === "api" ? "api" as const : item.kind === "csv" ? "csv" as const : null,
      rowsIn: safeCount(item.rows_in),
      rowsOk: safeCount(item.rows_ok),
      rowsRejected: safeCount(item.rows_rejected),
    }];
  }).sort((a, b) => (b.startedAt ?? "").localeCompare(a.startedAt ?? "") || b.id - a.id);
}

export function normalizeSources(overview: OverviewResponse | null, runs: RunView[]): SourceView[] {
  const entries = overview?.sources ?? overview?.entities ?? {};
  return FEEDS.map((feed) => {
    const entry: OverviewSource = entries[feed.entity] ?? {};
    const recent = runs.filter((run) => run.entity === feed.entity);
    const latest = recent[0] ?? null;
    // A partial run is not a successful checkpoint; do not infer success
    // from data_as_of or last_run_at.
    const success = recent.find((run) => run.status === "ok" && run.finishedAt);
    return {
      ...feed,
      status: feed.entity === "stock" ? "blocked" : safeStatus(entry.status ?? latest?.status),
      rows: feed.entity === "stock" ? null : safeCount(entry.rows),
      rejected: feed.entity === "stock" ? null : safeCount(entry.rejected),
      unmapped: feed.entity === "products" ? safeCount(entry.unmapped) : null,
      lastRunAt: timestamp(entry.last_run_at) ?? latest?.startedAt ?? null,
      dataAsOf: feed.entity === "stock" ? null : timestamp(entry.data_as_of),
      latestStatus: latest?.status ?? safeStatus(entry.status),
      lastSuccessfulAt: success?.finishedAt ?? null,
      reportedIntervalMin: safeCount(entry.interval_min),
    };
  });
}

export function normalizeRejects(input: unknown): RejectView[] {
  if (!input || typeof input !== "object") return [];
  const items = (input as { items?: unknown }).items;
  if (!Array.isArray(items)) return [];
  return (items as RejectResponse[]).map((item) => {
    const reasonCode = typeof item?.reason_code === "string" && Object.hasOwn(REASONS, item.reason_code)
      ? item.reason_code : "UNCLASSIFIED";
    return {
      id: safeCount(item?.id),
      reasonCode,
      detail: REASONS[reasonCode] ?? "A source record was rejected. Review in the restricted source system.",
    };
  });
}

export function normalizeMatrix(overview: OverviewResponse | null): MatrixView {
  const matrix = overview?.route_matrix;
  return {
    pairs: safeCount(matrix?.pairs),
    fallbackPairs: safeCount(matrix?.fallback_pairs),
    fetchedAt: timestamp(matrix?.fetched_at),
    provider: matrix?.provider === "ors" ? "OpenRouteService" :
      matrix?.provider === "fallback" ? "Estimated fallback" : null,
  };
}

export function normalizeScheduler(overview: OverviewResponse | null): SchedulerView {
  const scheduler = overview?.scheduler;
  const known = new Set(["ok", "failed", "running", "partial"]);
  return {
    lastTickAt: timestamp(scheduler?.last_tick_at),
    lastTickStatus: typeof scheduler?.last_tick_status === "string" &&
      known.has(scheduler.last_tick_status) ? scheduler.last_tick_status : null,
    reportedIntervalMin: safeCount(scheduler?.tick_interval_min),
    // Avoid rendering arbitrary job names from free-text responses or inferring
    // that an advertised job is actually running.
    jobs: Array.isArray(scheduler?.jobs) ? scheduler.jobs.filter(
      (job): job is string =>
        typeof job === "string" &&
        ["ingest_orders", "ingest_products", "ingest_inbound", "ingest_fleet", "stale_data_check"].includes(job)
    ) : [],
  };
}

export function summarizeRun(run: RunView): string {
  if (run.kind === "csv") return "CSV upload (filename hidden)";
  if (run.checkpointFrom || run.checkpointTo) {
    return [run.checkpointFrom ?? "Unknown start", run.checkpointTo ?? "Unknown end"].join(" → ");
  }
  return "Checkpoint not reported";
}
