/** T17: last known position only. Server filters by current trip assignment and on_road state. */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRightLeft, MapPin, RefreshCcw, Truck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { isApiError } from "../../api/client";
import { fetchLocations } from "../../api/locations";
import { PATHS } from "../../app/access";
import { useAuthStore } from "../../app/store";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { resolveTimeZone, type LocationWithTimeZone } from "../warehouse/prep-queue/timezone";
import {
  getEligibleDispatchers, getLiveTrips, handoverTrip,
  type LiveTrip,
} from "./trackingApi";

const INCIDENTS: Record<string, string> = {
  vehicle_breakdown: "Xe hỏng",
  traffic_or_accident: "Giao thông / tai nạn",
  site_inaccessible: "Không thể tiếp cận điểm giao",
  other: "Sự cố khác",
};
const RISK: Record<string, string> = {
  ON_TRACK: "Đúng kế hoạch",
  AT_RISK: "Có rủi ro",
  PREDICTED_LATE: "Dự kiến trễ",
  OVERDUE: "Quá hạn",
};
const RISK_COLOR: Record<string, string> = {
  green: "border-risk-onTrack-fg bg-surface",
  yellow: "border-border bg-chip",
  orange: "border-border bg-chip",
  red: "border-risk-predictedLate-fg bg-risk-lateRow",
};

function marketTime(value: string | null, zone: string | null): string {
  if (!value) return "Chưa có dữ liệu";
  if (!zone) return "Chưa xác định múi giờ market";
  const time = new Date(value);
  if (!Number.isFinite(time.getTime())) return "Chưa có dữ liệu";
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: zone, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    hour12: false,
  }).format(time);
}

function incidentText(value: string | null): string | null {
  if (!value) return null;
  return INCIDENTS[value] ?? "Sự cố đang mở";
}

function safeHandoverError(error: unknown): string {
  if (!isApiError(error)) return "Không thể bàn giao chuyến. Vui lòng thử lại.";
  if (error.code === "REASON_REQUIRED") return "Lý do bàn giao là bắt buộc.";
  if (error.code === "FORBIDDEN") return "Bạn không có quyền bàn giao chuyến này.";
  if (error.code === "NOT_FOUND") return "Chuyến không còn khả dụng trong market của bạn.";
  if (error.code === "VALIDATION_ERROR") return "Người nhận không còn đủ điều kiện. Hãy chọn lại.";
  if (error.status === 409) return "Phân công đã thay đổi. Vui lòng tải lại trước khi bàn giao.";
  return "Không thể bàn giao chuyến. Vui lòng thử lại.";
}

function TripRow({ trip, zone, onHandover }: {
  trip: LiveTrip; zone: string | null; onHandover: (tripId: number) => void;
}) {
  const hasBreakdown = trip.open_incident === "vehicle_breakdown";
  const eta = hasBreakdown ? "ETA không xác định" : marketTime(trip.forecast_eta, zone);
  const coords = trip.last_position
    ? trip.last_position.lat.toFixed(2) + ", " + trip.last_position.lon.toFixed(2)
    : "Chưa có vị trí";
  const riskLabel = trip.risk ? RISK[trip.risk.status] ?? "Chưa xác định" : "Chưa xác định";
  const color = trip.risk ? RISK_COLOR[trip.risk.color] ?? "border-border" : "border-border";
  const incident = incidentText(trip.open_incident);

  return (
    <li className="rounded-card border border-border bg-surface p-5" aria-label={"Chuyến " + trip.trip_id}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-ink">
            <Truck aria-hidden="true" className="h-5 w-5 text-pine" />
            <h2 className="text-h3 font-semibold">Chuyến #{trip.trip_id} · {trip.vehicle_code}</h2>
          </div>
          <p className="mt-1 text-sm text-inkMuted">Đơn #{trip.order_id} · đang trên đường</p>
        </div>
        <span className={"rounded-control border px-3 py-1 text-sm font-semibold " + color}>
          Rủi ro: {riskLabel}
        </span>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div>
          <p className="text-overline text-inkMuted">Vị trí gần nhất</p>
          <p className="mt-1 flex items-center gap-2 font-mono text-ink">
            <MapPin aria-hidden="true" className="h-4 w-4" /> {coords}
          </p>
        </div>
        <div>
          <p className="text-overline text-inkMuted">Giờ cập nhật</p>
          <p className="mt-1 font-mono text-ink">{marketTime(trip.updated_at, zone)}</p>
        </div>
        <div>
          <p className="text-overline text-inkMuted">ETA</p>
          <p className="mt-1 font-mono text-ink">{eta}</p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
        <div className="flex flex-col gap-2 text-sm text-inkMuted">
          <span>Quãng đường còn lại: {trip.remaining_km === null ? "Chưa xác định" : trip.remaining_km + " km"}</span>
          {trip.risk?.status === "PREDICTED_LATE" && <Link
            to={`${PATHS.notifications}?order_id=${trip.order_id}`} className="font-semibold underline">
            Review delay notice
          </Link>}
          {incident && <span role="status" className="flex items-center gap-2 text-risk-predictedLate-fg">
            <AlertTriangle aria-hidden="true" className="h-4 w-4" /> Sự cố mở: {incident}
          </span>}
        </div>
        <button
          type="button" onClick={() => onHandover(trip.trip_id)}
          className="inline-flex items-center gap-2 rounded-control border border-pine px-4 py-2 text-sm font-semibold text-pine"
        >
          <ArrowRightLeft aria-hidden="true" className="h-4 w-4" /> Bàn giao chuyến
        </button>
      </div>
    </li>
  );
}

export function TrackingList() {
  const user = useAuthStore((state) => state.user);
  const allowed = Boolean(user?.roles.includes("dispatcher"));
  const key = ["dispatcher-tracking-live", user?.id, user?.employee_id, user?.market];
  const live = useQuery({
    queryKey: key, enabled: allowed,
    queryFn: ({ signal }) => getLiveTrips(signal),
    retry: false, refetchOnWindowFocus: false,
  });
  const timezone = useQuery({
    queryKey: ["dispatcher-tracking-market-timezone", user?.id, user?.market],
    enabled: allowed,
    queryFn: async ({ signal }) => {
      const locations = await fetchLocations(signal);
      const zones = Array.from(new Set(locations
        .map((location) => resolveTimeZone(location as LocationWithTimeZone))
        .filter((zone): zone is string => Boolean(zone))));
      return zones.length === 1 ? zones[0] : null;
    },
    retry: false,
  });

  const [handoverTripId, setHandoverTripId] = useState<number | null>(null);
  const [recipient, setRecipient] = useState("");
  const [reason, setReason] = useState("");
  const [handoverError, setHandoverError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [hiddenTrips, setHiddenTrips] = useState<{ owner: number | null; ids: number[] }>({ owner: null, ids: [] });
  const candidates = useQuery({
    queryKey: ["t17-eligible-dispatchers", user?.id, user?.market, handoverTripId],
    enabled: allowed && handoverTripId !== null,
    queryFn: ({ signal }) => getEligibleDispatchers(handoverTripId!, signal),
    staleTime: 0,
    retry: false,
  });

  async function refreshTrips() {
    const result = await live.refetch();
    if (result.isSuccess) setHiddenTrips({ owner: null, ids: [] });
  }

  function openHandover(tripId: number) {
    setHandoverTripId(tripId);
    setRecipient("");
    setReason("");
    setHandoverError(null);
  }

  function closeHandover() {
    if (saving) return;
    setHandoverTripId(null);
    setRecipient("");
    setReason("");
    setHandoverError(null);
  }

  async function submitHandover(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || handoverTripId === null) return;
    const employee = Number(recipient);
    if (!reason.trim()) {
      setHandoverError("Lý do bàn giao là bắt buộc.");
      return;
    }
    if (!candidates.data?.some((c) => c.employee_id === employee)) {
      setHandoverError("Chọn Dispatcher đủ điều kiện.");
      return;
    }
    setSaving(true);
    setHandoverError(null);
    try {
      await handoverTrip(handoverTripId, employee, reason.trim());
      // Hide committed transfer immediately while refetching server-authorized rows.
      setHiddenTrips({ owner: user?.id ?? null, ids: [...(hiddenTrips.owner === user?.id ? hiddenTrips.ids : []), handoverTripId] });
      setHandoverTripId(null);
      setRecipient("");
      setReason("");
      await refreshTrips();
    } catch (error) {
      // Preserve selected receiver and reason: the user can correct either without losing data.
      setHandoverError(safeHandoverError(error));
    } finally {
      setSaving(false);
    }
  }

  if (!allowed) {
    return <section data-screen="TrackingList" role="alert">Dispatcher access required.</section>;
  }
  const rows = (live.data ?? []).filter((trip) =>
    hiddenTrips.owner !== user?.id || !hiddenTrips.ids.includes(trip.trip_id));
  const selectedTrip = (live.data ?? []).find((trip) => trip.trip_id === handoverTripId);
  return (
    <section data-screen="TrackingList" className="mx-auto max-w-6xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-overline font-semibold text-inkMuted">Dispatcher / Tracking</p>
          <h1 className="text-h1 font-semibold text-ink">Theo dõi chuyến được gán</h1>
          <p className="mt-2 text-sm text-inkMuted">
            Chỉ hiển thị vị trí mới nhất của chuyến đang chạy được backend phân công. Không có bản đồ hoặc lịch sử GPS.
          </p>
        </div>
        <button type="button" onClick={() => void refreshTrips()} disabled={live.isFetching}
          className="inline-flex items-center gap-2 rounded-control border border-border px-4 py-2 text-sm font-semibold">
          <RefreshCcw aria-hidden="true" className="h-4 w-4" /> Tải lại
        </button>
      </header>

      {timezone.isError || (timezone.isSuccess && !timezone.data) ? (
        <p role="status" className="text-sm text-inkMuted">Múi giờ market chưa xác minh; không hiển thị giờ theo máy người dùng.</p>
      ) : null}
      {live.isRefetchError && <p role="alert" className="text-sm text-risk-predictedLate-fg">Không tải lại được danh sách mới nhất. Dữ liệu hiện tại có thể đã thay đổi.</p>}
      {live.isPending ? <LoadingState rows={3} /> : live.isError ? (
        <ErrorState error={isApiError(live.error) && live.error.code === "FORBIDDEN"
          ? live.error : new Error("Không thể tải danh sách chuyến được gán.")}
          title="Không thể tải vị trí trực tiếp" onRetry={() => void refreshTrips()} />
      ) : rows.length === 0 ? (
        <EmptyState message="Không có chuyến đang chạy được gán cho bạn."
          action={{ label: "Tải lại", onClick: () => void refreshTrips() }} />
      ) : (
        <ul className="space-y-4" aria-label="Chuyến được gán">
          {rows.map((trip) => (
            <TripRow key={trip.trip_id} trip={trip} zone={timezone.data ?? null} onHandover={openHandover} />
          ))}
        </ul>
      )}

      {selectedTrip && (
        <div role="dialog" aria-modal="true" aria-labelledby="t17-handover-title"
          className="rounded-card border border-border bg-surface p-5 shadow-lg">
          <h2 id="t17-handover-title" className="text-h3 font-semibold">Bàn giao chuyến #{selectedTrip.trip_id}</h2>
          <p className="mt-1 text-sm text-inkMuted">Xe {selectedTrip.vehicle_code} · chỉ thay đổi chuyến này.</p>
          {candidates.isPending ? (
            <LoadingState rows={1} />
          ) : candidates.isError ? (
            <p role="alert" className="mt-4 text-sm text-risk-predictedLate-fg">
              Không tải được người nhận đủ điều kiện; không thể bàn giao.
            </p>
          ) : (
            <form className="mt-4 space-y-4" onSubmit={(event) => void submitHandover(event)}>
              <label className="block text-sm font-semibold" htmlFor="t17-recipient">Dispatcher nhận chuyến</label>
              <select id="t17-recipient" value={recipient} onChange={(event) => setRecipient(event.target.value)}
                className="w-full rounded-control border border-border bg-surface p-2" required>
                <option value="">Chọn Dispatcher đủ điều kiện</option>
                {candidates.data?.map((candidate) => (
                  <option key={candidate.employee_id} value={candidate.employee_id}>{candidate.display_name}</option>
                ))}
              </select>
              {candidates.data?.length === 0 && (
                <p role="status" className="text-sm text-inkMuted">Không có Dispatcher khác đủ điều kiện.</p>
              )}
              <label className="block text-sm font-semibold" htmlFor="t17-reason">Lý do bàn giao (bắt buộc)</label>
              <textarea id="t17-reason" value={reason} onChange={(event) => setReason(event.target.value)}
                className="w-full rounded-control border border-border bg-surface p-2"
                rows={3} maxLength={1000} required aria-required="true" />
              {!reason.trim() && <p className="text-sm text-inkMuted">Lý do bàn giao là bắt buộc.</p>}
              {handoverError && <p role="alert" className="text-sm text-risk-predictedLate-fg">{handoverError}</p>}
              <div className="flex flex-wrap gap-3">
                <button type="submit" disabled={saving || !reason.trim() || !recipient}
                  className="rounded-control bg-pine px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                  {saving ? "Đang bàn giao…" : "Xác nhận bàn giao"}
                </button>
                <button type="button" disabled={saving} onClick={closeHandover}
                  className="rounded-control border border-border px-4 py-2 text-sm">Hủy</button>
              </div>
            </form>
          )}
          {(candidates.isPending || candidates.isError) && (
            <button type="button" onClick={closeHandover} className="mt-4 rounded-control border border-border px-4 py-2 text-sm">
              Đóng
            </button>
          )}
        </div>
      )}
    </section>
  );
}
