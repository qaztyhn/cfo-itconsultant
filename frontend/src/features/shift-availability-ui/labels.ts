import type {
  AssignmentStatus,
  DriverEligibilityKind,
  EligibilityStatus,
  TaskPhase,
  WarningSeverity,
} from "./types";

/**
 * Display strings for the feature. English by default; a host app can pass overrides
 * (e.g. built from i18next) without this feature touching the shared i18n files.
 */
export interface ShiftAvailabilityLabels {
  warehouseTitle: string;
  driverTitle: string;
  officialShift: string;
  breakLabel: string;
  restPeriod: string;
  scheduleUnverified: string;
  scheduleUnverifiedHint: string;
  outsideSchedule: string;
  outsideScheduleHint: string;

  timelineLabel: string;
  noShiftInWindow: string;
  continuesBefore: string;
  continuesAfter: string;

  backendValidationNote: string;
  dutyTime: string;
  drivingTime: string;
  eligibilityTitle: string;
  warningsTitle: string;
  dataAsOf: string;
  loading: string;
  retry: string;
  correlationId: string;
  emptyDefault: string;
  errorDefault: string;
  unavailableDefault: string;
  assignmentStatus: Record<AssignmentStatus, string>;
  warningSeverity: Record<WarningSeverity, string>;
  eligibilityStatus: Record<EligibilityStatus, string>;
  eligibilityKind: Record<DriverEligibilityKind, string>;
  taskPhase: Record<TaskPhase, string>;
}

export const DEFAULT_LABELS: ShiftAvailabilityLabels = {
  warehouseTitle: "Warehouse staff shifts",
  driverTitle: "Driver shifts and availability",
  officialShift: "Official shift",
  breakLabel: "Break",
  restPeriod: "Rest period",
  scheduleUnverified: "Schedule not verified",
  scheduleUnverifiedHint: "No official schedule on file. Capacity is not counted until a manager confirms the schedule.",
  outsideSchedule: "Outside official schedule",
  outsideScheduleHint: "Display hint only. The backend validates scheduling.",
  
  timelineLabel: "Shift timeline",
  noShiftInWindow: "No official shift in this window",
  continuesBefore: "continues from before this window",
  continuesAfter: "continues after this window",

  backendValidationNote: "Final scheduling decisions are validated by the backend.",
  dutyTime: "Duty time",
  drivingTime: "Driving time",
  eligibilityTitle: "Driver eligibility",
  warningsTitle: "Scheduling warnings",
  dataAsOf: "Data as of",
  loading: "Loading…",
  retry: "Retry",
  correlationId: "Correlation ID",
  emptyDefault: "No shifts to show for this period",
  errorDefault: "Shift data could not be loaded",
  unavailableDefault: "Shift data is not available yet",
  assignmentStatus: {
    assigned: "Assigned",
    tentative: "Tentative",
    available: "Available",
    conflict: "Conflict",
    unavailable: "Unavailable",
  },
  warningSeverity: { info: "Info", warning: "Warning", blocking: "Blocking" },
  eligibilityStatus: { eligible: "Eligible", not_eligible: "Not eligible", unknown: "Unknown" },
  
  eligibilityKind: {
    rest: "Rest",
    driving_limit: "Driving limit",
    break: "Break",
    licence: "Licence",
    vehicle_scope: "Vehicle scope",
    history: "Driving history",
  },

  taskPhase: {
    prep: "Preparation",
    loading: "Loading",
    waiting: "Waiting",
    driving: "Driving",
    unloading: "Unloading",
    return: "Return",
  },
};

type NestedKey = "assignmentStatus" | "warningSeverity" | "eligibilityStatus" | "eligibilityKind" | "taskPhase";

export type ShiftAvailabilityLabelOverrides = Partial<Omit<ShiftAvailabilityLabels, NestedKey>> & {
  [K in NestedKey]?: Partial<ShiftAvailabilityLabels[K]>;
};

/** Merge overrides over the defaults, including the nested maps. */
export function mergeLabels(overrides?: ShiftAvailabilityLabelOverrides): ShiftAvailabilityLabels {
  if (!overrides) return DEFAULT_LABELS;
  return {
    ...DEFAULT_LABELS,
    ...overrides,
    assignmentStatus: { ...DEFAULT_LABELS.assignmentStatus, ...overrides.assignmentStatus },
    warningSeverity: { ...DEFAULT_LABELS.warningSeverity, ...overrides.warningSeverity },
    eligibilityStatus: { ...DEFAULT_LABELS.eligibilityStatus, ...overrides.eligibilityStatus },
    
    eligibilityKind: { ...DEFAULT_LABELS.eligibilityKind, ...overrides.eligibilityKind },

    taskPhase: { ...DEFAULT_LABELS.taskPhase, ...overrides.taskPhase },
  } as ShiftAvailabilityLabels;
}