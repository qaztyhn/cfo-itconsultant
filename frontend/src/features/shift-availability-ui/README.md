# Shift Availability UI

Reusable, isolated React components that show **shifts and availability** for warehouse staff and
drivers. They are built from synthetic fixtures while the shift-schedule API contract (Dev 1) is
still pending. Nothing here calls a backend.

Everything in this folder is presentation only. The backend decides what is allowed; this UI
displays the result it is given.

## What this feature does not do

- It does not call any API, router, store or shared client, and it imports no shared component
  (`StateViews`, `ApiError`, ...). It has its own `StatePanel`.
- It does not edit `src/i18n/en.json`. Strings come from `labels.ts` and can be overridden by prop.
- It does not compute legal limits. Rest, driving limits, breaks, licence, vehicle scope and
  history results are **already evaluated** by the data source; the UI only shows them, together
  with a reference code (`reasonCode`) and rule source (`ruleSource`).
- It does not suggest staffing or shift changes, and it does not compare against `expected_staff`
  (ASM-007).
- It shows no GPS, no personal data and no money values.
- Fixtures use invented names and ids (`Staff W02`, `Driver D01`, `DEMO-0001`).

## Quick preview

Render the demo anywhere (a test, a temporary local route that you do not commit):

```tsx
import { ShiftAvailabilityDemo } from "@/features/shift-availability-ui";

<ShiftAvailabilityDemo />;
```

The demo has a "Demo state" selector (ready, loading, empty, error, unavailable).

## Components

All components are exported from `index.ts`. Every component accepts an optional `labels`
(`ShiftAvailabilityLabelOverrides`) and, where it renders a container, a `className`.

### `WarehouseShiftPanel`

| Prop | Type | Notes |
|---|---|---|
| `state` | `PanelState<ShiftTimelineModel<WarehouseStaffRow>>` | See "Panel states". |
| `labels?` | `ShiftAvailabilityLabelOverrides` | |
| `className?` | `string` | |

Shows the title, "Data as of" (when `dataAsOf` is set), panel-level warnings, the timeline and the
note "Final scheduling decisions are validated by the backend."

### `DriverAvailabilityPanel`

| Prop | Type | Notes |
|---|---|---|
| `state` | `PanelState<ShiftTimelineModel<DriverRow>>` | See "Panel states". |
| `labels?` | `ShiftAvailabilityLabelOverrides` | |
| `className?` | `string` | |

Same as the warehouse panel, plus a per-driver block with **duty time** and **driving time**
(shown separately, exactly as supplied) and the eligibility list.

### `ShiftTimeline`

| Prop | Type | Notes |
|---|---|---|
| `model` | `ShiftTimelineModel<ShiftRow>` | Window, rows, optional panel warnings. |
| `ariaLabel?` | `string` | Defaults to the `timelineLabel` text. |
| `labels?` | `ShiftAvailabilityLabelOverrides` | |
| `className?` | `string` | |

Draws, per row: official shifts, breaks, driver rest periods, tasks (with phase and status), the
part of a task that falls outside the official shifts, and the row's warnings. Ranges are drawn as
real time spans, so a shift crossing midnight is one continuous block.

### `DriverEligibilityList`

| Prop | Type | Notes |
|---|---|---|
| `items` | `readonly DriverEligibilityItem[]` | Already-evaluated results. |
| `labels?` | `ShiftAvailabilityLabelOverrides` | |
| `className?` | `string` | |

`unknown` is its own state ("Unknown"). It is never rendered as eligible or as out of scope.

### `AssignmentStatusBadge`, `WarningList`, `StatePanel`

| Component | Props |
|---|---|
| `AssignmentStatusBadge` | `status: AssignmentStatus`, `labels?`, `className?` |
| `WarningList` | `warnings: readonly SchedulingWarning[]`, `labels?`, `showTitle?` (default `true`), `className?` |
| `StatePanel<T>` | `state: PanelState<T>`, `children: (data: T) => ReactNode`, `labels?`, `skeletonRows?` (default 4), `className?` |

## View models (local, not an API contract)

Defined in `types.ts`. These are **presentation types**, not backend response schemas. Their names
and shapes were chosen for display and may differ from the final API.

- `TimeRange { start, end }`: ISO 8601 strings **with an offset or `Z`**.
- `TimelineWindow extends TimeRange { timeZone }`: IANA name, used for display only.
- `ShiftTimelineModel<Row> { window, rows, warnings?, dataAsOf? }`.
- `WarehouseStaffRow` (`kind: "warehouse"`) and `DriverRow` (`kind: "driver"`, plus `restPeriods?`,
  `totals?`, `eligibility`). Both carry `scheduleStatus`, `shifts`, `tasks`, `status`, `warnings`.
- `ShiftBlock { id, range, label?, breaks? }`, `TaskBlock { id, range, label, status, phase? }`.
- `SchedulingWarning { id, severity, code, message, relatedTaskId?, ruleSource? }`.
- `DriverEligibilityItem { id, kind, status, summary, reasonCode?, ruleSource? }`.
- `PanelState<T>`: `loading | empty | error | unavailable | ready`.

### Schedule not verified vs. no shift

- `scheduleStatus: "unverified"` means there is no official schedule on file (DEC-SHIFTS-001, Q12d).
  The UI shows **"Schedule not verified"**. It never shows "no staff available".
- `scheduleStatus: "verified"` with an empty `shifts` array means a schedule exists but there is no
  shift in the window. The UI shows "No official shift in this window".

### Eligibility and reasons

Missing schedule, history, licence or vehicle scope fails closed (DEC-DEV2-D7-001). Show the
specific reason through `reasonCode` (for example `DRIVER_REST_INSUFFICIENT`,
`DRIVER_HISTORY_MISSING`, `VEHICLE_SCOPE_UNKNOWN`) so it is not confused with "no drivers
available". Duty time and driving time are separate (DEC-DRIVER-001); the caller supplies both.

An empty `eligibility` array means eligibility was **not evaluated**. The UI then shows
"Eligibility not evaluated"; an `available` assignment status must never be read as "meets every
requirement". Tasks and rest periods are drawn on the timeline even when a row has no official
shift or an unverified schedule.

### Outside the official schedule

`outsideShiftPortions` (in `time.ts`) is a **geometric display hint**: it marks the part of a task
that is not covered by any shift in the data. It encodes no rule and does not replace backend
validation. The UI says so: "Display hint only. The backend validates scheduling."

## Panel states

| `state.status` | Rendering |
|---|---|
| `loading` | Skeleton with `role="status"` and `aria-busy="true"`. |
| `empty` | Message (`message` or the default). Also shown for a `ready` state with zero rows. |
| `error` | `role="alert"`, the message, the `correlationId` (when given) and a Retry button (when `onRetry` is given). |
| `unavailable` | `role="status"` message. This means the source cannot supply data yet; it is not an error. |
| `ready` | The panel content. |

## Labels

English defaults are in `labels.ts` (`DEFAULT_LABELS`). A host app can pass overrides built from its
own i18n, for example:

```tsx
<WarehouseShiftPanel state={state} labels={{ retry: t("common.retry"), assignmentStatus: { assigned: t("...") } }} />
```

`mergeLabels` merges the nested maps (`assignmentStatus`, `warningSeverity`, `eligibilityStatus`,
`eligibilityKind`, `taskPhase`). Do not pass keys with an `undefined` value: an `undefined`
override replaces the default text. Omit the key instead.

## Accessibility and responsive behaviour

- Status is never shown by colour alone: every status has an icon and text; outside-schedule parts
  use a dashed border, an icon and text in the list.
- Colours come only from Tailwind tokens (`tailwind.config.ts`). No hex values.
- New warnings are announced through `aria-live="polite"`.
- From `md` up, the timeline is drawn on a time axis inside its own horizontally scrolling
  container, so the page itself does not scroll sideways. The drawn lane is `aria-hidden`; the same
  facts are in a text list that stays available to screen readers.
- Below `md`, the text list is the main view.
- Time labels use 24-hour "HH:mm" in `window.timeZone`.

## Future API integration

The components take **view models**. When Dev 1 publishes the shift-schedule and eligibility
contract, add a mapper (outside this feature, or in a new file here) from the API response to
`ShiftTimelineModel<...>`. Do not change the components to read API field names directly.

| Area | What integration needs | Owner |
|---|---|---|
| Official shift schedule | `hr.employee_shift_schedule` and the `shift-schedule` API are **proposals** under review (DEC-SHIFTS-001), not a contract yet. A DTO for shifts, breaks and verification status is needed. | Dev 1 |
| Driver eligibility | A DTO for already-evaluated results (rest, driving limit, break, licence, vehicle scope, history), with reason codes and rule sources. | Dev 1 |
| Reason and warning codes | A canonical list of codes. The codes `TASK_OUTSIDE_SHIFT` and `SCHEDULE_PARTIAL` in `fixtures.ts` are **demo codes only, not API codes**. | Dev 1 |
| Time zone and time format | Source of the time zone (`market.timezone`) and ISO 8601 timestamps with offset. | Dev 1 |
| Test data | 56 days of driver history and future shifts, plus synthetic vehicle and driver seeds (DEC-DEV2-D7-001, D7-E). Not implemented yet. | Dev 2 |
| Plan review wiring | Mapper, i18next labels and placing the panels on the Plan review screen. Out of scope for this feature. | Integration |

`ASM-008` is a proposal that is not approved; this feature does not depend on it.

## Tests

Tests live next to the code (`*.test.ts`, `*.test.tsx`). Run only this feature:

```bash
npx vitest run src/features/shift-availability-ui
```

They cover time maths (midnight crossing, clipping, outside-shift hint, invalid input), every
component, all five panel states, and the fixture scenarios (W05, W06, W07, D02 to D06).