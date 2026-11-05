/**
 * Hàng đợi sự kiện offline (IndexedDB) cho driver PWA (US-EXE-03; 09 mục 9).
 * Mỗi sự kiện có idempotency_key và occurred_at = giờ chạm; gửi lại theo thứ tự khi có mạng; trùng key không tạo bản sao.
 * Owner: Dev 3 (luồng C) — M6.
 */
export interface QueuedEvent {
  orderId: number;
  eventType: "DISPATCHED" | "DELIVERED" | "FAILED";
  occurredAt: string;
  idempotencyKey: string;
  payload: Record<string, unknown>;
}

export async function enqueue(event: QueuedEvent): Promise<void> {
  void event; // TODO(#M6-offline)
}

export async function flush(): Promise<number> {
  return 0; // TODO(#M6-offline)
}
