/**
 * Synthetic demo fixtures for the Shift Availability UI.
 *
 * All data is invented: no real people, no customer data, no GPS. Staff and driver names are
 * placeholders. Reason codes and rule sources are copied from the approved decision register
 * (docs/ASSUMPTIONS.md) for display only; the summaries intentionally carry no numeric limits,
 * because this UI never evaluates rest / driving rules (the backend does).
 * Timestamps use a fixed +01:00 offset purely for the demo.
 */
import type {
  DriverRow,
  ShiftTimelineModel,
  TimelineWindow,
  WarehouseStaffRow,
} from "./types";

const DAYS = ["2026-11-09", "2026-11-10"] as const;

/** Build a demo timestamp: at("06:00") is 09 Nov, at("02:00", 1) is 10 Nov. */
function at(time: string, dayOffset: 0 | 1 = 0): string {
  return `${DAYS[dayOffset]}T${time}:00+01:00`;
}

export const DEMO_WINDOW: TimelineWindow = {
  start: at("04:00"),
  end: at("04:00", 1),
  timeZone: "Europe/Stockholm",
};

export const DEMO_WAREHOUSE_ROWS: WarehouseStaffRow[] = [
  {
    kind: "warehouse",
    id: "wh-w02",
    displayName: "Staff W02",
    role: "Operator",
    scheduleStatus: "verified",
    status: "assigned",
    shifts: [
      { id: "wh-w02-s1", label: "Early shift", range: { start: at("06:00"), end: at("14:00") }, breaks: [{ start: at("10:00"), end: at("10:30") }] },
    ],
    tasks: [
      { id: "wh-w02-t1", label: "Prep DEMO-0001", phase: "prep", status: "assigned", range: { start: at("07:00"), end: at("09:30") } },
    ],
    warnings: [],
  },
  {
    kind: "warehouse",
    id: "wh-w03",
    displayName: "Staff W03",
    role: "Operator",
    scheduleStatus: "verified",
    status: "tentative",
    shifts: [{ id: "wh-w03-s1", label: "Late shift", range: { start: at("14:00"), end: at("22:00") } }],
    tasks: [
      { id: "wh-w03-t1", label: "Prep DEMO-0002", phase: "prep", status: "tentative", range: { start: at("15:00"), end: at("17:00") } },
    ],
    warnings: [],
  },
  {
    kind: "warehouse",
    id: "wh-w04",
    displayName: "Staff W04",
    role: "Forklift operator",
    scheduleStatus: "verified",
    status: "available",
    shifts: [{ id: "wh-w04-s1", label: "Early shift", range: { start: at("06:00"), end: at("14:00") } }],
    tasks: [],
    warnings: [],
  },
  {
    kind: "warehouse",
    id: "wh-w05",
    displayName: "Staff W05",
    role: "Operator",
    scheduleStatus: "verified",
    status: "conflict",
    shifts: [{ id: "wh-w05-s1", label: "Early shift", range: { start: at("06:00"), end: at("14:00") } }],
    tasks: [
      { id: "wh-w05-t1", label: "Prep DEMO-0003", phase: "prep", status: "conflict", range: { start: at("12:30"), end: at("15:30") } },
    ],
    warnings: [
      {
        id: "wh-w05-w1",
        severity: "warning",
        code: "TASK_OUTSIDE_SHIFT",
        message: "Task DEMO-0003 runs past the end of the official shift.",
        relatedTaskId: "wh-w05-t1",
        ruleSource: "DEC-DRIVER-001",
      },
    ],
  },
  {
    kind: "warehouse",
    id: "wh-w06",
    displayName: "Staff W06",
    role: "Operator",
    scheduleStatus: "unverified",
    status: "unavailable",
    shifts: [],
    tasks: [],
    warnings: [],
  },
  {
    kind: "warehouse",
    id: "wh-w07",
    displayName: "Staff W07",
    role: "Operator",
    // Verified schedule with no shift on this day: not the same as an unverified schedule.
    scheduleStatus: "verified",
    status: "unavailable",
    shifts: [],
    tasks: [],
    warnings: [],
  },
];

export const DEMO_DRIVER_ROWS: DriverRow[] = [
  {
    kind: "driver",
    id: "dr-d01",
    displayName: "Driver D01",
    scheduleStatus: "verified",
    status: "assigned",
    shifts: [{ id: "dr-d01-s1", label: "Day shift", range: { start: at("06:00"), end: at("15:00") }, breaks: [{ start: at("11:30"), end: at("12:15") }] }],
    restPeriods: [{ start: at("04:00"), end: at("06:00") }],
    totals: { dutyMinutes: 390, drivingMinutes: 300 },
    tasks: [
      { id: "dr-d01-t1", label: "Load DEMO-0001", phase: "loading", status: "assigned", range: { start: at("07:00"), end: at("07:45") } },
      { id: "dr-d01-t2", label: "Drive DEMO-0001", phase: "driving", status: "assigned", range: { start: at("07:45"), end: at("10:15") } },
      { id: "dr-d01-t3", label: "Unload DEMO-0001", phase: "unloading", status: "assigned", range: { start: at("10:15"), end: at("11:00") } },
      { id: "dr-d01-t4", label: "Return", phase: "return", status: "assigned", range: { start: at("11:00"), end: at("13:30") } },
    ],
    eligibility: [
      { id: "dr-d01-e1", kind: "rest", status: "eligible", summary: "Rest requirement met before this shift.", ruleSource: "DEC-DRIVER-001" },
      { id: "dr-d01-e2", kind: "driving_limit", status: "eligible", summary: "Planned driving is within the configured limits.", ruleSource: "DEC-DRIVER-001" },
      { id: "dr-d01-e3", kind: "break", status: "eligible", summary: "Break eligibility satisfied.", ruleSource: "DEC-DRIVER-001" },
      { id: "dr-d01-e4", kind: "licence", status: "eligible", summary: "Licence valid for the shift." },
    ],
    warnings: [],
  },
  {
    kind: "driver",
    id: "dr-d02",
    displayName: "Driver D02",
    scheduleStatus: "verified",
    status: "conflict",
    shifts: [{ id: "dr-d02-s1", label: "Late shift", range: { start: at("14:00"), end: at("23:00") } }],
    restPeriods: [{ start: at("04:00"), end: at("14:00") }],
    totals: { dutyMinutes: 270, drivingMinutes: 180 },
    tasks: [
      { id: "dr-d02-t1", label: "Drive DEMO-0004", phase: "driving", status: "conflict", range: { start: at("14:30"), end: at("17:30") } },
      { id: "dr-d02-t2", label: "Unload DEMO-0004", phase: "unloading", status: "conflict", range: { start: at("17:30"), end: at("19:00") } },
    ],
    eligibility: [
      {
        id: "dr-d02-e1",
        kind: "rest",
        status: "not_eligible",
        summary: "Rest before this shift is not sufficient.",
        reasonCode: "DRIVER_REST_INSUFFICIENT",
        ruleSource: "DEC-DRIVER-001",
      },
    ],
    warnings: [
      {
        id: "dr-d02-w1",
        severity: "blocking",
        code: "DRIVER_REST_INSUFFICIENT",
        message: "Driver rest is insufficient; this plan cannot be approved.",
        relatedTaskId: "dr-d02-t1",
        ruleSource: "DEC-DRIVER-001",
      },
    ],
  },
  {
    kind: "driver",
    id: "dr-d03",
    displayName: "Driver D03",
    scheduleStatus: "verified",
    status: "unavailable",
    shifts: [{ id: "dr-d03-s1", label: "Day shift", range: { start: at("06:00"), end: at("15:00") } }],
    tasks: [],
    eligibility: [
      {
        id: "dr-d03-e1",
        kind: "history",
        status: "unknown",
        summary: "Required work and rest history is missing.",
        reasonCode: "DRIVER_HISTORY_MISSING",
        ruleSource: "DEC-DEV2-D7-001",
      },
      { id: "dr-d03-e2", kind: "driving_limit", status: "unknown", summary: "Cannot be evaluated without history.", ruleSource: "DEC-DEV2-D7-001" },
    ],
    warnings: [
      {
        id: "dr-d03-w1",
        severity: "blocking",
        code: "DRIVER_HISTORY_MISSING",
        message: "Work and rest history is missing; no approvable plan can be offered.",
        ruleSource: "DEC-DEV2-D7-001",
      },
    ],
  },
  {
    kind: "driver",
    id: "dr-d04",
    displayName: "Driver D04",
    scheduleStatus: "verified",
    status: "tentative",
    shifts: [{ id: "dr-d04-s1", label: "Day shift", range: { start: at("08:00"), end: at("17:00") } }],
    tasks: [
      { id: "dr-d04-t1", label: "Drive DEMO-0005", phase: "driving", status: "tentative", range: { start: at("09:00"), end: at("12:00") } },
    ],
    eligibility: [
      {
        id: "dr-d04-e1",
        kind: "vehicle_scope",
        status: "unknown",
        summary: "Regulation scope of the assigned vehicle is not classified.",
        reasonCode: "VEHICLE_SCOPE_UNKNOWN",
        ruleSource: "DEC-DEV2-D7-001",
      },
    ],
    warnings: [
      {
        id: "dr-d04-w1",
        severity: "warning",
        code: "VEHICLE_SCOPE_UNKNOWN",
        message: "Vehicle scope is unknown; eligibility cannot be confirmed.",
        relatedTaskId: "dr-d04-t1",
        ruleSource: "DEC-DEV2-D7-001",
      },
    ],
  },
  {
    kind: "driver",
    id: "dr-d05",
    displayName: "Driver D05",
    scheduleStatus: "unverified",
    status: "unavailable",
    shifts: [],
    tasks: [],
    eligibility: [],
    warnings: [],
  },
  {
    kind: "driver",
    id: "dr-d06",
    displayName: "Driver D06",
    scheduleStatus: "verified",
    status: "assigned",
    // Shift crossing midnight (DEC-SHIFTS-001 Q12a).
    shifts: [{ id: "dr-d06-s1", label: "Night shift", range: { start: at("18:00"), end: at("02:00", 1) }, breaks: [{ start: at("22:00"), end: at("22:45") }] }],
    restPeriods: [{ start: at("04:00"), end: at("18:00") }],
    totals: { dutyMinutes: 360, drivingMinutes: 270 },
    tasks: [
      { id: "dr-d06-t1", label: "Drive DEMO-0006", phase: "driving", status: "assigned", range: { start: at("19:00"), end: at("23:30") } },
      { id: "dr-d06-t2", label: "Return", phase: "return", status: "assigned", range: { start: at("23:30"), end: at("01:00", 1) } },
    ],
    eligibility: [
      { id: "dr-d06-e1", kind: "rest", status: "eligible", summary: "Rest requirement met before this shift.", ruleSource: "DEC-DRIVER-001" },
      { id: "dr-d06-e2", kind: "driving_limit", status: "eligible", summary: "Planned driving is within the configured limits.", ruleSource: "DEC-DRIVER-001" },
    ],
    warnings: [],
  },
];

export const DEMO_WAREHOUSE_MODEL: ShiftTimelineModel<WarehouseStaffRow> = {
  window: DEMO_WINDOW,
  rows: DEMO_WAREHOUSE_ROWS,
  dataAsOf: "10:05",
  warnings: [
    {
      id: "wh-panel-w1",
      severity: "info",
      code: "SCHEDULE_PARTIAL",
      message: "One staff member has no verified schedule and adds no capacity.",
      ruleSource: "DEC-SHIFTS-001",
    },
  ],
};

export const DEMO_DRIVER_MODEL: ShiftTimelineModel<DriverRow> = {
  window: DEMO_WINDOW,
  rows: DEMO_DRIVER_ROWS,
  dataAsOf: "10:05",
};