/**
 * View models for the isolated Shift Availability UI.
 *
 * These are LOCAL presentation types. They are NOT API response schemas and must not be
 * treated as a contract with the backend (see README "Future API integration").
 * Values such as rest / driving limits are never computed here: the backend (or a future
 * mapper) supplies the already-evaluated result and this UI only displays it.
 */

/** ISO 8601 timestamps WITH an offset or "Z", e.g. "2026-11-09T06:00:00+01:00". */
export interface TimeRange {
  start: string;
  end: string;
}

/** Visible time window of a timeline. `timeZone` is an IANA name used for display only. */
export interface TimelineWindow extends TimeRange {
  timeZone: string;
}

export type AssignmentStatus = "assigned" | "tentative" | "available" | "conflict" | "unavailable";

export type WarningSeverity = "info" | "warning" | "blocking";

/** Whether an official schedule exists for the person (DEC-SHIFTS-001 Q12d). */
export type ScheduleVerification = "verified" | "unverified";

/** Duty phases are shown separately from driving (DEC-DRIVER-001 / D7-C). */
export type TaskPhase = "prep" | "loading" | "waiting" | "driving" | "unloading" | "return";

export interface ShiftBlock {
  id: string;
  range: TimeRange;
  /** e.g. "Early shift". */
  label?: string;
  /** Official breaks inside the shift. */
  breaks?: TimeRange[];
}

export interface TaskBlock {
  id: string;
  range: TimeRange;
  /** Public task / order reference. Must not contain customer PII. */
  label: string;
  status: AssignmentStatus;
  phase?: TaskPhase;
}

export interface SchedulingWarning {
  id: string;
  severity: WarningSeverity;
  /** Reference code supplied by the data source, e.g. "DRIVER_REST_INSUFFICIENT". Display only. */
  code: string;
  message: string;
  relatedTaskId?: string;
  /** Where the rule comes from, e.g. "DEC-DRIVER-001". Display only. */
  ruleSource?: string;
}

export type EligibilityStatus = "eligible" | "not_eligible" | "unknown";

export type DriverEligibilityKind =
  | "rest"
  | "driving_limit"
  | "break"
  | "licence"
  | "vehicle_scope"
  | "history";

/** An already-evaluated eligibility result. `unknown` must never be shown as eligible. */
export interface DriverEligibilityItem {
  id: string;
  kind: DriverEligibilityKind;
  status: EligibilityStatus;
  summary: string;
  reasonCode?: string;
  ruleSource?: string;
}

interface PersonRowBase {
  id: string;
  /** Synthetic display name. */
  displayName: string;
  role?: string;
  scheduleStatus: ScheduleVerification;
  /** Empty when `scheduleStatus` is "unverified". */
  shifts: ShiftBlock[];
  tasks: TaskBlock[];
  status: AssignmentStatus;
  warnings: SchedulingWarning[];
}

export interface WarehouseStaffRow extends PersonRowBase {
  kind: "warehouse";
}

export interface DriverRow extends PersonRowBase {
  kind: "driver";
  /** Rest periods between shifts, shown on the timeline. */
  restPeriods?: TimeRange[];
  /** Totals shown as supplied; duty and driving time are separate. */
  totals?: { dutyMinutes?: number; drivingMinutes?: number };
  eligibility: DriverEligibilityItem[];
}

export type ShiftRow = WarehouseStaffRow | DriverRow;

export interface ShiftTimelineModel<Row extends ShiftRow> {
  window: TimelineWindow;
  rows: Row[];
  /** Panel-level warnings that do not belong to a single row. */
  warnings?: SchedulingWarning[];
  /** Optional "Data as of" label supplied by the caller. */
  dataAsOf?: string;
}

export interface PanelError {
  message: string;
  correlationId?: string;
}

/** Loading / empty / error / unavailable / ready states shared by every panel. */
export type PanelState<T> =
  | { status: "loading" }
  | { status: "empty"; message?: string }
  | { status: "error"; error: PanelError; onRetry?: () => void }
  | { status: "unavailable"; message?: string }
  | { status: "ready"; data: T };