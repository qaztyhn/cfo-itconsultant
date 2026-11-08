/**
 * ShiftAvailabilityDemo — renders both panels with synthetic fixtures so the feature can be
 * previewed without a router, AppShell or backend. Not used by the app; not an API example.
 */
import { useId, useState } from "react";
import { DEMO_DRIVER_MODEL, DEMO_WAREHOUSE_MODEL } from "../fixtures";
import type { ShiftAvailabilityLabelOverrides } from "../labels";
import type { PanelState } from "../types";
import { DriverAvailabilityPanel } from "./DriverAvailabilityPanel";
import { WarehouseShiftPanel } from "./WarehouseShiftPanel";

type DemoMode = "ready" | "loading" | "empty" | "error" | "unavailable";

const MODES: readonly DemoMode[] = ["ready", "loading", "empty", "error", "unavailable"];

function toState<T>(mode: DemoMode, data: T, onRetry: () => void): PanelState<T> {
  switch (mode) {
    case "loading":
      return { status: "loading" };
    case "empty":
      return { status: "empty" };
    case "error":
      return {
        status: "error",
        error: { message: "Demo error: shift data could not be loaded.", correlationId: "demo-corr-0001" },
        onRetry,
      };
    case "unavailable":
      return { status: "unavailable" };
    default:
      return { status: "ready", data };
  }
}

export interface ShiftAvailabilityDemoProps {
  labels?: ShiftAvailabilityLabelOverrides;
}

export function ShiftAvailabilityDemo({ labels }: ShiftAvailabilityDemoProps) {
  const [mode, setMode] = useState<DemoMode>("ready");
  const selectId = useId();
  const retry = () => setMode("ready");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2 text-body text-ink">
        <label htmlFor={selectId} className="font-semibold">
          Demo state
        </label>
        <select
          id={selectId}
          value={mode}
          onChange={(e) => setMode(e.target.value as DemoMode)}
          className="rounded-control border bg-surface px-2 py-1 text-body"
        >
          {MODES.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <span className="text-caption text-inkMuted">Synthetic demo data</span>
      </div>
      <WarehouseShiftPanel state={toState(mode, DEMO_WAREHOUSE_MODEL, retry)} labels={labels} />
      <DriverAvailabilityPanel state={toState(mode, DEMO_DRIVER_MODEL, retry)} labels={labels} />
    </div>
  );
}