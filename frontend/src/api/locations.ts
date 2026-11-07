/**
 * Lời gọi danh sách địa điểm (kho, cửa hàng). Owner: Dev 3 (luồng C) — M0.
 * GIẢ ĐỊNH (cần Dev 1 xác nhận): GET /locations trả { items: [{ id, code, name, type }] } như MSW handler; 06 chưa định nghĩa.
 * DEPENDENCY: thay kiểu viết tay bằng kiểu sinh từ OpenAPI khi có schema.d.ts.
 */
import { apiGet } from "./client";

export interface WorkLocation {
  id: number;
  code: string;
  name: string;
  type: string;
}

export async function fetchLocations(signal?: AbortSignal): Promise<WorkLocation[]> {
  const response = await apiGet<{ items: WorkLocation[] }>("/locations", undefined, signal);
  return response.items;
}