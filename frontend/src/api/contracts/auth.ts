/**
 * TẠM THỜI — hợp đồng xác thực theo docs/06 mục 4 và mục 2 (quyết định #2: viết tay vì chưa có schema.d.ts).
 * DEPENDENCY: thay file này bằng kiểu sinh từ OpenAPI (`npm run gen:api`) khi Dev 1 xuất schema, rồi xóa file.
 * Owner: Dev 3 (luồng C) — M0.
 */

/** ref.user_role (docs/05, docs/06 mục 2). Không thêm vai trò mới. */
export const USER_ROLES = ["admin", "dispatcher", "warehouse", "sales", "driver", "customer_service", "viewer"] as const;
export type UserRole = (typeof USER_ROLES)[number];

/** kpi_scopes (docs/06 mục 3.1): revenue_all = Business owner, ops = KPI vận hành. */
export type KpiScope = "revenue_all" | "ops";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthUser {
  id: number;
  employee_id: number | null;
  name: string | null;
  roles: UserRole[];
  market: string | null;
  location_ids: number[];
  locale: string;
  kpi_scopes: KpiScope[];
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  /** Giây; 28800 = 8 giờ. */
  expires_in: number;
  user: AuthUser;
}