import { describe, expect, it } from "vitest";
import { evidence, orders, skuDetails, suggestions } from "./model";

describe("US-PLN-07 AC1 evidence and checked dates",()=>{
  it("projects only verified fields and never invents feasible dates",()=>{
    const view=evidence({result:"infeasible",failed_check:"stock",dates_searched:[
      {date:"2026-11-09",result:"FAIL",check:"STOCK"},{result:"FIRST_FEASIBLE"}],
      per_warehouse_checks:[{warehouse:"STO",stock:{passed:false,code:"STOCK_SHORT"}}],
      rejected_candidates:[{code:"NO_TRUCK_FIT",detail:{message:"customer@email.test"}}]});
    expect(view.earliest).toBeNull();
    expect(view.checkedDates).toHaveLength(1);
    expect(view.warehouseChecks[0].code).toBe("STOCK_SHORT");
    expect(JSON.stringify(view)).not.toContain("customer@email.test");
  });
});
describe("US-APR-04 AC1/AC3 suggestion display",()=>{
  it("keeps run ID as reference without claiming a hold",()=>{
    const view=suggestions({items:[
      {id:1,order_id:9,type:"REPLAN_SUGGESTED",resolved:false,details:{run_id:44,private:"PRIVATE"}},
      {id:2,order_id:10,type:"REPLAN_SUGGESTED",resolved:true,details:{run_id:55}},
      {id:3,order_id:11,type:"OTHER",details:{run_id:66}}]});
    expect(view).toHaveLength(1);
    expect(view[0]).toMatchObject({orderId:9,runId:44});
    expect(JSON.stringify(view)).not.toContain("PRIVATE");
    expect(evidence({kind:"replan_suggestion",hold_expires_at:null}).hold).toBeNull();
  });
});
describe("ASM-005 legacy blocked SKU",()=>{
  it("keeps only blocked or infeasible statuses and safe SKU refs",()=>{
    const view=orders({items:[
      {id:1,status:"BLOCKED_UNMAPPED_SKU",order_no:"SE-001",block_reason:"SKU_UNMAPPED"},
      {id:2,status:"APPROVED",order_no:"SE-002"}]});
    expect(view).toHaveLength(1);
    expect(view[0].ref).toBe("SE-001");
    expect(skuDetails({lines:[
      {local_sku:"SE-SKU-1",mapping_status:"PENDING",name:"Private Name"},
      {local_sku:"user@example.com",mapping_status:"PENDING"},
      {local_sku:"SE-SKU-2",mapping_status:"CONFIRMED"}]})).toEqual([{code:"SE-SKU-1",status:"PENDING"}]);
  });
});
