import { describe, expect, it } from "vitest";
import { PAGE_SIZE, projectDetail, projectPage, validPage } from "./model";

describe("US-ORD-02 AC1 store response isolation",()=>{
  it("projects only IDs granted by the authenticated store assignment",()=>{
    const page=projectPage({items:[
      {id:1,origin_store:{id:21,code:"ST-21"},order_no:"SE-1",status:"APPROVED",
        committed_date:"2026-11-11",promise_end:"2026-11-11T12:00:00Z"},
      {id:2,origin_store:{id:22,code:"ST-22"},order_no:"SE-2",status:"PLANNED"},
      {id:3,origin_store:{id:21},order_no:"SE-3",status:"SUBMITTED"},
    ],total:3},[21],1,PAGE_SIZE);
    expect(page.items.map(x=>x.reference)).toEqual(["SE-1","SE-3"]);
    expect(page.items[0].promisedEnd).toBe("2026-11-11T12:00:00Z");
    expect(page.items[1].promisedEnd).toBeNull();
    expect(page.total).toBe(3);
  });
  it("does not treat unscoped responses as authorized",()=>{
    expect(projectPage({items:[{id:1,order_no:"SE-1"}]},[21],1,PAGE_SIZE).items).toEqual([]);
    expect(projectPage({items:[{id:1,origin_store:{id:21}}]},[],1,PAGE_SIZE).items).toEqual([]);
  });
});
describe("US-ORD-02 AC2 out of scope detail",()=>{
  it("fails closed on mismatched order/store and projects safe Sales fields",()=>{
    const data={id:12,origin_store:{id:22},order_no:"SE-12",status:"APPROVED",
      risk:{forecast_eta:"2026-11-12T13:00:00Z",driver_gps:"PRIVATE"},
      contact:{phone:"PRIVATE"},delivery:{address:"PRIVATE",lat:1,lon:2},
      lines:[{line_no:1,name:"Cement",qty_sale:2,sale_unit:"bag"}]};
    expect(projectDetail(data,[21],12)).toBeNull();
    const permitted=projectDetail(data,[22],12);
    expect(permitted?.forecastEta).toBe("2026-11-12T13:00:00Z");
    expect(permitted?.lines).toEqual([{number:1,product:"Cement",quantity:"2",unit:"bag"}]);
    expect(JSON.stringify(permitted)).not.toContain("PRIVATE");
    expect(projectDetail(data,[22],13)).toBeNull();
  });
});
describe("US-ORD-02 AC3 query/page safety",()=>{
  it("validates pagination and dates without manufacturing delivery commitments",()=>{
    expect(validPage("2")).toBe(2);
    expect(validPage("-2")).toBe(1);
    expect(validPage("1e9")).toBe(1);
    const data=projectPage({items:[{id:1,origin_store:{id:21},
      date_request:{date_to:"2026-99-99"},committed_date:null,
      promise_end:"INVALID",status:"SUBMITTED"}]},[21],1,PAGE_SIZE);
    expect(data.items[0]).toMatchObject({requestedDate:null,committedDate:null,promisedEnd:null});
  });
});
