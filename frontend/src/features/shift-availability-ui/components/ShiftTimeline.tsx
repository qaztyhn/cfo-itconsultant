/**
 * ShiftTimeline — official shifts, breaks, rest periods and tasks on a time axis.
 * Presentation only: it draws what it is given. The "outside official schedule" mark is a
 * geometric display hint (see time.ts) and never replaces backend validation.
 * From `md` up the lane is drawn on a horizontally scrollable axis; below `md` the same
 * information is shown as a text list. The list stays available to screen readers on `md`+.
 */
import type { ReactNode } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight } from "lucide-react";
import { mergeLabels, type ShiftAvailabilityLabelOverrides, type ShiftAvailabilityLabels } from "../labels";
import { ASSIGNMENT_STATUS_CLASS } from "../styles";
import { formatClock, hourTicks, outsideShiftPortions, rangeToPercent, toMs } from "../time";
import type {
  ShiftRow,
  ShiftTimelineModel,
  TaskBlock,
  TimeRange,
  TimelineWindow,
} from "../types";
import { AssignmentStatusBadge } from "./AssignmentStatusBadge";
import { WarningList } from "./WarningList";

export interface ShiftTimelineProps {
  model: ShiftTimelineModel<ShiftRow>;
  labels?: ShiftAvailabilityLabelOverrides;
  /** Accessible name of the timeline region. Defaults to the "timelineLabel" text. */
  ariaLabel?: string;
  className?: string;
}

function clockRange(range: TimeRange, timeZone: string): string {
  return `${formatClock(range.start, timeZone)}–${formatClock(range.end, timeZone)}`;
}

function clipNote(range: TimeRange, win: TimelineWindow, text: ShiftAvailabilityLabels): string {
  const pos = rangeToPercent(range, win);
  if (!pos) return "";
  const notes: string[] = [];
  if (pos.clippedStart) notes.push(text.continuesBefore);
  if (pos.clippedEnd) notes.push(text.continuesAfter);
  return notes.length > 0 ? ` (${notes.join(", ")})` : "";
}

/** Parts of a task outside the official shifts. Unverified rows have no official shift to compare. */
function outsideOf(row: ShiftRow, task: TaskBlock): TimeRange[] {
  return row.scheduleStatus === "verified" ? outsideShiftPortions(task.range, row.shifts) : [];
}

interface BlockProps {
  range: TimeRange;
  win: TimelineWindow;
  kind: string;
  title: string;
  className: string;
  children?: ReactNode;
}

function Block({ range, win, kind, title, className, children }: BlockProps) {
  const pos = rangeToPercent(range, win);
  if (!pos) return null;
  return (
    <div
      data-kind={kind}
      title={title}
      className={["absolute flex items-center gap-0.5 overflow-hidden px-1 text-caption", className].join(" ")}
      style={{ left: `${pos.left}%`, width: `${pos.width}%` }}
    >
      {pos.clippedStart && <ChevronLeft aria-hidden="true" className="h-3 w-3 shrink-0" />}
      {children}
      {pos.clippedEnd && <ChevronRight aria-hidden="true" className="ml-auto h-3 w-3 shrink-0" />}
    </div>
  );
}

interface RowProps {
  row: ShiftRow;
  win: TimelineWindow;
  ticks: string[];
  text: ShiftAvailabilityLabels;
  labels?: ShiftAvailabilityLabelOverrides;
}

function TimelineRow({ row, win, ticks, text, labels }: RowProps) {
  const tz = win.timeZone;
  const unverified = row.scheduleStatus === "unverified";
  const restPeriods = row.kind === "driver" ? (row.restPeriods ?? []) : [];
  const warnedTaskIds = new Set(
    row.warnings.map((w) => w.relatedTaskId).filter((id): id is string => Boolean(id)),
  );
  const span = toMs(win.end) - toMs(win.start);

  return (
    <li data-row-id={row.id} data-schedule={row.scheduleStatus} className="py-3">
      <div className="grid gap-2 md:grid-cols-[10rem_1fr] md:gap-0">
        <div className="min-w-0 pr-3">
          <p className="truncate text-body font-semibold text-ink">{row.displayName}</p>
          {row.role && <p className="truncate text-caption text-inkMuted">{row.role}</p>}
          <AssignmentStatusBadge status={row.status} labels={labels} className="mt-1" />
        </div>

        <div className="min-w-0">
          {unverified ? (
            <div
              role="note"
              className="flex items-start gap-2 rounded-control bg-risk-atRisk-bg px-3 py-2 text-body text-risk-atRisk-fg"
            >
              <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-semibold">{text.scheduleUnverified}</p>
                <p>{text.scheduleUnverifiedHint}</p>
              </div>
            </div>
          ) : (
            <>
              {row.shifts.length === 0 && (
                <p className="rounded-control bg-chip px-3 py-2 text-body text-inkMuted">{text.noShiftInWindow}</p>
              )}
              {row.shifts.length > 0 && (
                <div aria-hidden="true" className="relative mx-5 hidden h-16 md:block">
                  {ticks.map((t) => (
                    <span
                      key={t}
                      className="absolute bottom-0 top-0 border-l border-border"
                      style={{ left: `${span > 0 ? ((toMs(t) - toMs(win.start)) / span) * 100 : 0}%` }}
                    />
                  ))}
                  {row.shifts.map((s) => (
                    <Block
                      key={s.id}
                      range={s.range}
                      win={win}
                      kind="shift"
                      title={`${text.officialShift}: ${clockRange(s.range, tz)}`}
                      className="top-1 h-4 rounded bg-navActive text-pine border"
                    >
                      <span className="truncate">{s.label ?? text.officialShift}</span>
                    </Block>
                  ))}
                  {row.shifts.flatMap((s) =>
                    (s.breaks ?? []).map((b, i) => (
                      <Block
                        key={`${s.id}-b${i}`}
                        range={b}
                        win={win}
                        kind="break"
                        title={`${text.breakLabel}: ${clockRange(b, tz)}`}
                        className="top-1 h-4 rounded bg-pine text-surface"
                      />
                    )),
                  )}
                  {restPeriods.map((r, i) => (
                    <Block
                      key={`rest-${i}`}
                      range={r}
                      win={win}
                      kind="rest"
                      title={`${text.restPeriod}: ${clockRange(r, tz)}`}
                      className="top-1 h-4 rounded border border-dashed bg-stone text-inkMuted"
                    >
                      <span className="truncate">{text.restPeriod}</span>
                    </Block>
                  ))}
                  {row.tasks.map((task) => {
                    const phase = task.phase ? text.taskPhase[task.phase] : undefined;
                    return (
                      <Block
                        key={task.id}
                        range={task.range}
                        win={win}
                        kind="task"
                        title={[task.label, phase, text.assignmentStatus[task.status], clockRange(task.range, tz)]
                          .filter(Boolean)
                          .join(" · ")}
                        className={["top-7 h-7 rounded", ASSIGNMENT_STATUS_CLASS[task.status]].join(" ")}
                      >
                        {warnedTaskIds.has(task.id) && (
                          <AlertTriangle aria-hidden="true" className="h-3 w-3 shrink-0" />
                        )}
                        <span className="truncate">{task.label}</span>
                      </Block>
                    );
                  })}
                  {row.tasks.flatMap((task) =>
                    outsideOf(row, task).map((part, i) => (
                      <Block
                        key={`${task.id}-out-${i}`}
                        range={part}
                        win={win}
                        kind="outside-schedule"
                        title={`${text.outsideSchedule}: ${clockRange(part, tz)}`}
                        className="top-7 h-7 rounded border-2 border-dashed border-apricot bg-risk-lateRow/60 text-risk-predictedLate-fg"
                      >
                        <AlertTriangle className="h-3 w-3 shrink-0" />
                      </Block>
                    )),
                  )}
                </div>
              )}
            </>
          )}

          <ul className="mt-2 flex flex-col gap-1 text-caption text-ink md:sr-only md:mt-0">
            {row.shifts.map((s) => (
              <li key={s.id}>
                {text.officialShift}
                {s.label ? ` (${s.label})` : ""}: {clockRange(s.range, tz)}
                {clipNote(s.range, win, text)}
                {(s.breaks ?? []).map((b) => `; ${text.breakLabel} ${clockRange(b, tz)}`).join("")}
              </li>
            ))}
            {restPeriods.map((r, i) => (
              <li key={`rest-${i}`}>
                {text.restPeriod}: {clockRange(r, tz)}
              </li>
            ))}
            {row.tasks.map((task) => {
              const outside = outsideOf(row, task);
              return (
                <li key={task.id}>
                  {task.label}
                  {task.phase ? ` · ${text.taskPhase[task.phase]}` : ""} · {text.assignmentStatus[task.status]} ·{" "}
                  {clockRange(task.range, tz)}
                  {clipNote(task.range, win, text)}
                  {outside.length > 0 &&
                    ` · ${text.outsideSchedule}: ${outside.map((p) => clockRange(p, tz)).join(", ")}`}
                </li>
              );
            })}
          </ul>

          {row.warnings.length > 0 && <WarningList warnings={row.warnings} labels={labels} showTitle={false} className="mt-2" />}
        </div>
      </div>
    </li>
  );
}

export function ShiftTimeline({ model, labels, ariaLabel, className }: ShiftTimelineProps) {
  const text = mergeLabels(labels);
  const win = model.window;
  const ticks = hourTicks(win);
  const span = toMs(win.end) - toMs(win.start);
  const anyOutside = model.rows.some((row) => row.tasks.some((t) => outsideOf(row, t).length > 0));

  return (
    <section aria-label={ariaLabel ?? text.timelineLabel} className={className}>
      <div className="overflow-x-auto">
        <div className="md:min-w-[960px]">
          <div aria-hidden="true" className="hidden md:grid md:grid-cols-[10rem_1fr]">
            <div />
            <div className="relative mx-5 h-6">
              {ticks.map((t, i) =>
                i % 2 === 0 ? (
                  <span
                    key={t}
                    className="absolute -translate-x-1/2 font-mono text-caption text-inkMuted"
                    style={{ left: `${span > 0 ? ((toMs(t) - toMs(win.start)) / span) * 100 : 0}%` }}
                  >
                    {formatClock(t, win.timeZone)}
                  </span>
                ) : null,
              )}
            </div>
          </div>
          <ul className="divide-y divide-border">
            {model.rows.map((row) => (
              <TimelineRow key={row.id} row={row} win={win} ticks={ticks} text={text} labels={labels} />
            ))}
          </ul>
        </div>
      </div>
      {anyOutside && <p className="mt-2 text-caption text-inkMuted">{text.outsideScheduleHint}</p>}
    </section>
  );
}