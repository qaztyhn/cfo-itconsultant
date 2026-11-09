/**
 * Chi tiết một đơn cho CS: trạng thái, khung giờ cam kết, ETA/rủi ro, liên hệ đã mask.
 * Không GPS, không toạ độ, không điểm số, không nút reveal. Dữ liệu đã qua allowlist trong api.ts.
 * Nơi gọi truyền key={orderId} để đổi đơn thì state chi tiết reset hoàn toàn.
 * Owner: Dev 3 (luồng C).
 */
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { RiskChip } from "../../components/RiskChip";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusChip } from "../../components/StatusChip";
import { CONTACT_HIDDEN } from "./allowlist";
import { csKeys, fetchOrderDetail } from "./api";
import { formatUtc, orDash, toOrderStatus, toRiskColor, toRiskLevel } from "./format";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="font-mono text-overline uppercase text-inkMuted">{label}</dt>
      <dd className="text-body text-ink">{children}</dd>
    </div>
  );
}

/** Hiện thẳng chuỗi đã mask từ server (không qua MaskedText, không tự mask); thiếu/không hợp lệ → "Contact hidden". */
function MaskedValue({ value, hiddenLabel }: { value: string | null; hiddenLabel: string }) {
  if (!value) return <span>{CONTACT_HIDDEN}</span>;
  return (
    <span className="font-mono">
      <span aria-hidden="true">{value}</span>
      <span className="sr-only">{hiddenLabel}</span>
    </span>
  );
}

export function OrderDetail({ orderId }: { orderId: number }) {
  const detail = useQuery({
    queryKey: csKeys.detail(orderId),
    queryFn: ({ signal }) => fetchOrderDetail(orderId, signal),
    retry: false,
    refetchInterval: false,
  });

  if (detail.isPending) {
    return <LoadingState rows={3} rowClassName="h-12" />;
  }
  if (detail.isError) {
    return <ErrorState error={detail.error} title="Order details unavailable" onRetry={() => void detail.refetch()} />;
  }

  const order = detail.data;
  const risk = order.risk;
  const window = order.committed.promiseStart || order.committed.promiseEnd
    ? `${formatUtc(order.committed.promiseStart)} – ${formatUtc(order.committed.promiseEnd)}`
    : "—";

  return (
    <div className="flex flex-col gap-6">
      <dl className="grid gap-4 sm:grid-cols-2">
        <Field label="Order no.">{order.orderNo}</Field>
        <Field label="External ref">{orDash(order.externalRef)}</Field>
        <Field label="Customer">{orDash(order.customerName)}</Field>
        <Field label="Status">{order.status ? <StatusChip status={toOrderStatus(order.status)} /> : "—"}</Field>
        <Field label="Submitted">{formatUtc(order.submittedAt)}</Field>
        <Field label="Committed date">{orDash(order.committed.date)}</Field>
        <Field label="Delivery window">{window}</Field>
        <Field label="Risk">
          {risk ? (
            <span className="flex flex-wrap items-center gap-2">
              <RiskChip level={toRiskLevel(risk.status)} color={toRiskColor(risk.color)} />
              <span>ETA {formatUtc(risk.forecastEta)}</span>
            </span>
          ) : (
            "—"
          )}
        </Field>
      </dl>

      <section aria-labelledby={`contact-${order.id}`} className="flex flex-col gap-3">
        <h3 id={`contact-${order.id}`} className="text-h3 text-ink">
          Contact
        </h3>
        <dl className="grid gap-4 sm:grid-cols-3">
          <Field label="Name">{orDash(order.contact.name)}</Field>
          <Field label="Phone">
            <MaskedValue value={order.contact.phone} hiddenLabel="Phone number (hidden)" />
          </Field>
          <Field label="Email">
            <MaskedValue value={order.contact.email} hiddenLabel="Email address (hidden)" />
          </Field>
        </dl>
        <p className="text-caption text-inkMuted">Contact details are masked by the server. They cannot be revealed here.</p>
      </section>
    </div>
  );
}