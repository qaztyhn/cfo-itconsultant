/** Synthetic demonstration only. No API calls, credentials, GPS, customer/driver PII or business calculations. */
import type {
  MilestoneTimelineModel,
  NotificationHistoryModel,
  OrderEventLogModel,
  RiskExplanationModel,
  RiskSummaryModel,
  TimeDatum,
  VehicleStatusModel,
} from "./types";

const verified = (at: string, source = "synthetic_order_events"): TimeDatum => ({
  at,
  quality: "verified",
  source,
});
const missing: TimeDatum = { at: null, quality: "missing" };

export const onTrackRisk: RiskSummaryModel = {
  timeZone: "Europe/Stockholm",
  committedWindow: {
    start: verified("2026-11-12T09:00:00Z"),
    end: verified("2026-11-12T11:30:00Z"),
    confirmedAt: verified("2026-11-11T12:00:00Z"),
  },
  plannedEta: verified("2026-11-12T10:15:00Z", "approved_plan"),
  forecastEta: verified("2026-11-12T10:25:00Z", "eta_forecast"),
  reserveConsumptionPct: { value: 13, quality: "verified", source: "eta_forecast" },
  risk: { status: "ON_TRACK", quality: "verified" },
  forecastProvenance: { source: "eta_forecast", asOf: "2026-11-12T09:30:00Z", routeQuality: "verified_ors" },
};

export const atRisk: RiskSummaryModel = {
  ...onTrackRisk,
  forecastEta: verified("2026-11-12T11:15:00Z", "eta_forecast"),
  reserveConsumptionPct: { value: 82, quality: "verified", source: "eta_forecast" },
  risk: { status: "AT_RISK", quality: "verified" },
};

export const predictedLate: RiskSummaryModel = {
  ...onTrackRisk,
  forecastEta: verified("2026-11-12T12:15:00Z", "eta_forecast"),
  reserveConsumptionPct: { value: 120, quality: "verified", source: "eta_forecast" },
  risk: { status: "PREDICTED_LATE", quality: "verified" },
  forecastProvenance: {
    source: "approved_routing_fallback",
    asOf: "2026-11-12T09:45:00Z",
    routeQuality: "estimated_fallback",
  },
};

export const missingForecast: RiskSummaryModel = {
  ...onTrackRisk,
  forecastEta: missing,
  reserveConsumptionPct: { value: null, quality: "unknown" },
  risk: { status: null, quality: "unknown" },
  forecastProvenance: { source: null, routeQuality: "unknown" },
};

export const staleRisk: RiskSummaryModel = {
  ...onTrackRisk,
  forecastEta: { at: "2026-11-12T10:25:00Z", quality: "stale", source: "eta_forecast" },
  reserveConsumptionPct: { value: 13, quality: "stale", source: "eta_forecast" },
  risk: { status: "ON_TRACK", quality: "stale" },
};

export const milestones: MilestoneTimelineModel = {
  timeZone: "Europe/Stockholm",
  asOf: verified("2026-11-12T09:50:00Z"),
  milestones: [
    { kind: "APPROVED", planned: verified("2026-11-11T12:00:00Z"), actual: verified("2026-11-11T12:01:00Z") },
    { kind: "START_PREP", planned: verified("2026-11-12T06:00:00Z"), actual: verified("2026-11-12T06:06:00Z") },
    { kind: "GOODS_READY", planned: verified("2026-11-12T07:00:00Z"), actual: verified("2026-11-12T07:08:00Z") },
    { kind: "LOADED", planned: verified("2026-11-12T07:45:00Z"), actual: verified("2026-11-12T07:48:00Z") },
    { kind: "DISPATCHED", planned: verified("2026-11-12T08:00:00Z"), actual: verified("2026-11-12T08:02:00Z") },
    { kind: "DELIVERED", planned: verified("2026-11-12T10:15:00Z"), actual: missing,
      forecast: verified("2026-11-12T10:25:00Z", "eta_forecast") },
  ],
};

export const multiVehicle: VehicleStatusModel = {
  timeZone: "Europe/Stockholm",
  overallForecastEta: verified("2026-11-12T12:15:00Z", "eta_forecast"),
  forecastProvenance: { source: "approved_routing_fallback", routeQuality: "estimated_fallback" },
  vehicles: [
    { tripReference: "T-101", vehicleCode: "STO-12-04", state: "DELIVERED", stateQuality: "verified",
      latestEventAt: verified("2026-11-12T10:30:00Z") },
    { tripReference: "T-102", vehicleCode: "STO-18-01", state: "DISPATCHED", stateQuality: "verified",
      forecastEta: verified("2026-11-12T12:15:00Z") },
    { tripReference: "T-103", vehicleCode: "STO-CR-01", state: "FAILED", stateQuality: "verified",
      latestEventAt: verified("2026-11-12T10:40:00Z") },
  ],
};

export const lateExplanation: RiskExplanationModel = {
  risk: { status: "PREDICTED_LATE", quality: "verified" },
  explanation: "Goods ready was recorded after the plan. The supplied forecast is beyond the committed window.",
  reasonCodes: ["GOODS_READY_LATE", "FORECAST_AFTER_PROMISE"],
  provenance: { source: "eta_forecast", asOf: "2026-11-12T09:45:00Z", routeQuality: "estimated_fallback" },
};

export const atRiskExplanation: RiskExplanationModel = {
  risk: { status: "AT_RISK", quality: "verified" },
  explanation: "Goods ready has not been recorded. Forecast is within the committed window but flagged at risk by the service.",
  reasonCodes: ["GOODS_READY_NOT_RECORDED"],
  provenance: { source: "eta_forecast", asOf: "2026-11-12T09:30:00Z" },
};

export const eventLog: OrderEventLogModel = {
  timeZone: "Europe/Stockholm",
  events: [
    { eventId: "E-1", eventAt: verified("2026-11-11T12:01:00Z"), eventType: "PLAN_APPROVED",
      actorRole: "Dispatcher", effect: "Approved plan recorded" },
    { eventId: "E-2", eventAt: verified("2026-11-12T07:08:00Z"), eventType: "GOODS_READY",
      actorRole: "Warehouse", effect: "Warehouse milestone recorded" },
    { eventId: "E-3", eventAt: verified("2026-11-12T09:45:00Z"), eventType: "RISK · PREDICTED_LATE",
      actorRole: "System", effect: "Dispatcher alert recorded" },
  ],
};

export const notifications: NotificationHistoryModel = {
  timeZone: "Europe/Stockholm",
  notifications: [
    { notificationId: "N-1", type: "CONFIRMED", channel: "email", status: "sent",
      timestamp: verified("2026-11-11T12:05:00Z") },
    { notificationId: "N-2", type: "DISPATCHED", channel: "sms_sim", status: "sent",
      timestamp: verified("2026-11-12T08:02:00Z") },
    { notificationId: "N-3", type: "DELAY", channel: "email", status: "draft",
      timestamp: verified("2026-11-12T09:45:00Z") },
  ],
};
