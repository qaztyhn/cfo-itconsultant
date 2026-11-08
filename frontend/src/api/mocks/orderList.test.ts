/**
 * Đối chiếu listOrders với docs/06 mục 5.4 (v1.4): phân trang, sắp xếp, bộ lọc, hình dạng phần tử.
 * Owner: Dev 3 (luồng C).
 */
import { describe, expect, it } from "vitest";
import { listOrders, type OrderRecord } from "./orderList";

const rec = (o: Partial<OrderRecord> & Pick<OrderRecord, "id">): OrderRecord => ({
  order_no: `SE-2026-${String(o.id).padStart(6, "0")}`,
  external_ref: null,
  status: "SUBMITTED",
  customer_name: "Customer",
  site: "Göteborg",
  warehouse: null,
  origin_store: { id: 101, code: "GBG-V" },
  date_request: { mode: "exact", date_from: null, date_to: null },
  committed_date: null,
  promise_end: null,
  risk_color: null,
  block_reason: null,
  total_amount: "0.00",
  currency: "SEK",
  submitted_at: "2026-11-04T08:00:00Z",
  ...o,
});

// Thời điểm (UTC): r5 = 11-03 08:00Z; r3 = r4 = 06:00Z; r1 = r6 = 06:30Z; r2 = 06:45Z (cùng ngày 04/11).
// So chuỗi sẽ xếp r2 trước r3/r4 vì "06:45:00Z" < "07:00:00+01:00"; so theo thời điểm thì r3/r4 trước r2.
const RECORDS: OrderRecord[] = [
  rec({ id: 1, external_ref: "POS-1", customer_name: "Nordbygg AB", status: "SUBMITTED", submitted_at: "2026-11-04T07:30:00+01:00",
    date_request: { mode: "exact", date_from: "2026-11-10", date_to: "2026-11-10" } }),
  rec({ id: 2, external_ref: "ERP-77", customer_name: "Skånska Kakel AB", status: "PREPARING", submitted_at: "2026-11-04T06:45:00Z",
    warehouse: { id: 2, code: "STO" }, date_request: { mode: "latest", date_from: null, date_to: "2026-11-06" },
    committed_date: "2026-11-05", promise_end: "2026-11-05T14:00:00+01:00", risk_color: "orange" }),
  rec({ id: 3, customer_name: "Östra Bygg", status: "LOADED", submitted_at: "2026-11-04T07:00:00+01:00",
    warehouse: { id: 2, code: "STO" }, origin_store: { id: 102, code: "STO-N" },
    date_request: { mode: "exact", date_from: "2026-11-05", date_to: "2026-11-05" },
    committed_date: "2026-11-05", promise_end: "2026-11-05T10:00:00+01:00", risk_color: "red" }),
  rec({ id: 4, external_ref: "POS-4", customer_name: "Malmö Entre", status: "APPROVED", submitted_at: "2026-11-04T06:00:00Z",
    warehouse: { id: 3, code: "MLM" }, origin_store: { id: 102, code: "STO-N" },
    date_request: { mode: "exact", date_from: "2026-11-07", date_to: "2026-11-07" },
    committed_date: "2026-11-07", promise_end: "2026-11-07T16:00:00+01:00", risk_color: "green" }),
  rec({ id: 5, customer_name: "Legacy Co", status: "BLOCKED_UNMAPPED_SKU", submitted_at: "2026-11-03T09:00:00+01:00",
    block_reason: "Unmapped SKU" }),
  rec({ id: 6, external_ref: "POS-6", customer_name: "Nordbygg AB", status: "SUBMITTED", submitted_at: "2026-11-04T07:30:00+01:00",
    date_request: { mode: "window", date_from: "2026-11-12", date_to: "2026-11-14" } }),
];

function run(query = "") {
  const result = listOrders(RECORDS, new URLSearchParams(query));
  if (!result.ok) throw new Error(result.message);
  return result.body;
}
const ids = (query = "") => run(query).items.map((i) => i.id);

describe("listOrders: sắp xếp (docs/06 mục 5.4)", () => {
  it("mặc định submitted_at ASC, id ASC — so theo thời điểm, không so chuỗi", () => {
    expect(ids()).toEqual([5, 3, 4, 1, 6, 2]);
  });

  it("sort=-submitted_at giảm dần, đơn trùng thời điểm vẫn id ASC", () => {
    expect(ids("sort=-submitted_at")).toEqual([2, 1, 6, 3, 4, 5]);
  });

  it("promise_end: NULL xếp cuối, kể cả khi giảm dần", () => {
    expect(ids("sort=promise_end")).toEqual([3, 2, 4, 1, 5, 6]);
    expect(ids("sort=-promise_end")).toEqual([4, 2, 3, 1, 5, 6]);
  });

  it("date_to (ngày yêu cầu): NULL xếp cuối", () => {
    expect(ids("sort=date_to")).toEqual([3, 2, 4, 1, 6, 5]);
  });

  it("committed_date: cùng giá trị thì id ASC, NULL cuối", () => {
    expect(ids("sort=committed_date")).toEqual([2, 3, 4, 1, 5, 6]);
  });

  it("order_no giảm dần", () => {
    expect(ids("sort=-order_no")).toEqual([6, 5, 4, 3, 2, 1]);
  });

  it("nhiều khoá: sort=status,-order_no", () => {
    expect(ids("sort=status,-order_no")).toEqual([4, 5, 3, 2, 6, 1]);
  });

  it("trường sort lạ → lỗi (422 ở handler)", () => {
    const result = listOrders(RECORDS, new URLSearchParams("sort=customer_name"));
    expect(result).toMatchObject({ ok: false });
    expect(result.ok ? "" : result.message).toContain("customer_name");
  });
});

describe("listOrders: phân trang", () => {
  it("mặc định page=1, page_size=50 và trả {items, page, page_size, total}", () => {
    const body = run();
    expect(body).toMatchObject({ page: 1, page_size: 50, total: 6 });
    expect(body.items).toHaveLength(6);
  });

  it("cắt đúng trang, total là tổng sau lọc", () => {
    expect(run("page=2&page_size=2")).toMatchObject({ page: 2, page_size: 2, total: 6 });
    expect(ids("page=2&page_size=2")).toEqual([4, 1]);
    expect(ids("page=4&page_size=2")).toEqual([]); // quá trang → rỗng, total vẫn 6
    expect(run("page=4&page_size=2").total).toBe(6);
  });

  it.each(["page=0", "page=abc", "page_size=0", "page_size=201", "page_size=-1"])("%s → lỗi", (query) => {
    expect(listOrders(RECORDS, new URLSearchParams(query))).toMatchObject({ ok: false });
  });

  it("page_size=200 là hợp lệ", () => {
    expect(listOrders(RECORDS, new URLSearchParams("page_size=200"))).toMatchObject({ ok: true });
  });
});

describe("listOrders: bộ lọc", () => {
  it("status", () => expect(ids("status=SUBMITTED")).toEqual([1, 6]));
  it("risk_color", () => expect(ids("risk_color=orange")).toEqual([2]));

  it("committed_date_from/to (đơn chưa có ngày cam kết bị loại khi lọc)", () => {
    expect(ids("committed_date_from=2026-11-06")).toEqual([4]);
    expect(ids("committed_date_to=2026-11-05")).toEqual([3, 2]);
    expect(ids("committed_date_from=2026-11-05&committed_date_to=2026-11-05")).toEqual([3, 2]);
  });

  it("warehouse_id / store_id; id ngoài phạm vi → danh sách rỗng", () => {
    expect(ids("warehouse_id=2")).toEqual([3, 2]);
    expect(ids("warehouse_id=99")).toEqual([]);
    expect(ids("store_id=102")).toEqual([3, 4]);
    expect(listOrders(RECORDS, new URLSearchParams("warehouse_id=abc"))).toMatchObject({ ok: false });
  });

  it("date_mode", () => {
    expect(ids("date_mode=latest")).toEqual([2]);
    expect(ids("date_mode=window")).toEqual([6]);
  });

  it("blocked=true chỉ BLOCKED_UNMAPPED_SKU; blocked=false loại chúng", () => {
    expect(ids("blocked=true")).toEqual([5]);
    expect(ids("blocked=false")).toEqual([3, 4, 1, 6, 2]);
  });

  it("q khớp order_no, external_ref, tên khách; không phân biệt hoa thường", () => {
    expect(ids("q=pos-1")).toEqual([1]); // external_ref
    expect(ids("q=erp-77")).toEqual([2]);
    expect(ids("q=NORDBYGG")).toEqual([1, 6]); // tên khách
    expect(ids("q=SE-2026-000004")).toEqual([4]); // order_no
    expect(ids("q=zzz")).toEqual([]);
  });
});

describe("listOrders: hình dạng phần tử", () => {
  it("đúng các trường của mục 5.4 và không lộ external_ref", () => {
    const item = run("q=erp-77").items[0];
    expect(Object.keys(item).sort()).toEqual([
      "block_reason", "committed_date", "currency", "customer_name", "date_request", "id", "order_no", "origin_store",
      "promise_end", "risk_color", "site", "status", "submitted_at", "total_amount", "warehouse",
    ]);
    expect(item).toMatchObject({
      warehouse: { id: 2, code: "STO" },
      origin_store: { id: 101, code: "GBG-V" },
      date_request: { mode: "latest", date_from: null, date_to: "2026-11-06" },
      submitted_at: "2026-11-04T06:45:00Z",
    });
  });
});