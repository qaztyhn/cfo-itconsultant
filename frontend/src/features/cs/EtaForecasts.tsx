/**
 * Lịch sử phiên bản ETA (GET /orders/{id}/eta-forecasts). Chỉ forecast_eta và risk_status; không điểm số nội bộ.
 * DEPENDENCY: endpoint hiện là stub phía backend; lỗi được hiện như "unavailable", không dựng dữ liệu giả.
 */
import { useQuery } from "@tanstack/react-query";
import { RiskChip } from "../../components/RiskChip";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { csKeys, fetchEtaForecasts } from "./api";
import { CsSection } from "./CsSection";
import { formatUtc, toRiskLevel } from "./format";

export function EtaForecasts({ orderId }: { orderId: number }) {
  const eta = useQuery({
    queryKey: csKeys.eta(orderId),
    queryFn: ({ signal }) => fetchEtaForecasts(orderId, signal),
    retry: false,
    refetchInterval: false,
  });

  function body() {
    if (eta.isPending) return <LoadingState rows={2} rowClassName="h-10" />;
    if (eta.isError) {
      return <ErrorState error={eta.error} title="ETA history unavailable" onRetry={() => void eta.refetch()} />;
    }
    if (eta.data.length === 0) return <p className="text-body text-inkMuted">No ETA forecasts yet.</p>;
    return (
      <ul className="flex flex-col gap-2">
        {eta.data.map((forecast, index) => (
          <li key={`${forecast.version ?? "v"}-${index}`} className="flex flex-wrap items-center gap-3 rounded-card border bg-surface px-4 py-2">
            <span className="font-mono text-body text-ink">Version {forecast.version ?? "—"}</span>
            <span className="text-body text-ink">ETA {formatUtc(forecast.forecastEta)}</span>
            <RiskChip level={toRiskLevel(forecast.riskStatus)} />
          </li>
        ))}
      </ul>
    );
  }

  return <CsSection title="ETA history">{body()}</CsSection>;
}