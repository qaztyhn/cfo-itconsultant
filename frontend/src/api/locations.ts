/**
 * Lời gọi danh sách địa điểm (kho, cửa hàng). Owner: Dev 3 (luồng C) — M0.
 * Đã xác nhận với backend thật: GET /locations trả { items: [{ id, code, name, type }] }, phân trang theo market.
 * DEPENDENCY: thay kiểu viết tay bằng kiểu sinh từ OpenAPI khi có schema.d.ts.
 */
import { apiGet } from "./client";

export interface WorkLocation {
  id: number;
  code: string;
  name: string;
  type: string;
}

/** Backend phân trang (mặc định 50, tối đa 200 dòng/trang); lấy tối đa mỗi trang để ít lần gọi nhất. */
const PAGE_SIZE = 200;
/** Chặn vòng lặp vô hạn nếu server trả dữ liệu bất thường. */
const MAX_PAGES = 50;

interface LocationsPage {
  items: WorkLocation[];
  page?: number;
  page_size?: number;
  total?: number;
}

/** Đọc TẤT CẢ trang của GET /locations; dừng khi đủ `total` hoặc trang cuối chưa đầy (mock không trả total). */
export async function fetchLocations(signal?: AbortSignal): Promise<WorkLocation[]> {
  const all: WorkLocation[] = [];
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const response = await apiGet<LocationsPage>("/locations", { page, page_size: PAGE_SIZE }, signal);
    all.push(...response.items);

    const size = response.page_size ?? PAGE_SIZE;
    const reachedTotal = typeof response.total === "number" && all.length >= response.total;
    if (response.items.length === 0 || response.items.length < size || reachedTotal) {
      break;
    }
  }
  return all;
}