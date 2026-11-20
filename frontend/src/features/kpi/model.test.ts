import {describe,it,expect} from "vitest";
import {CARDS, METRICS, dailyPoints, decisions, displayValue, metricValue, supportingValue, validDate} from "./model";
describe("US-KPI-01 AC1 five cards and approved metric keys",()=>{
  it("renders five cards covering exactly the five approved server keys",()=>{
    expect(CARDS).toHaveLength(5);
    expect(CARDS.flat().sort()).toEqual(METRICS.map(m=>m.key).sort());
  });
  it("shows missing metrics and baselines as unavailable, never zero",()=>{
    expect(metricValue({metrics:{planning_time_min:{value:4.2,baseline:15}}},"planning_time_min"))
      .toMatchObject({value:4.2,baseline:15,change:null,sales:null,dispatcher:null});
    expect(displayValue(null,"percent")).toBe("Chưa có dữ liệu");
    expect(metricValue({metrics:{on_time_rate:{value:null}}},"on_time_rate").value).toBeNull();
    expect(displayValue(0,"percent")).toBe("0%");
  });
  it("reads Sales/Dispatcher and three supporting values without inventing missing data",()=>{
    const response={metrics:{planning_time_min:{value:4.2,by_path:{sales:2.1,dispatcher:6}},
      eta_error_min:{median:18,p90:52,target:{median:20,p90:60}}},
      supporting:{order_to_commit_min:{by_path:{sales:6,dispatcher:95}},
        counter_commit_rate:{value:0.42},manual_plan_count:{value:6}}};
    expect(metricValue(response,"planning_time_min")).toMatchObject({sales:2.1,dispatcher:6});
    expect(metricValue(response,"eta_error_min")).toMatchObject({median:18,p90:52,targetMedian:20,targetP90:60,baseline:null});
    expect(supportingValue(response,"order_to_commit_min")).toMatchObject({sales:6,dispatcher:95});
    expect(supportingValue(response,"counter_commit_rate").value).toBe(0.42);
    expect(supportingValue(response,"manual_plan_count").value).toBe(6);
  });
});
describe("US-KPI-01 AC1 daily trends",()=>{
  it("accepts only market-local supplied days and numeric values",()=>{
    expect(dailyPoints({points:[
      {day:"2026-11-11",value:null},{day:"2026-11-10",value:0.72},
      {day:"2026-99-99",value:999},{day:"2026-11-09",value:"0.8"},
    ]})).toEqual([
      {day:"2026-11-09",value:null},{day:"2026-11-10",value:0.72},
      {day:"2026-11-11",value:null},
    ]);
    expect(validDate("2026-02-30")).toBeNull();
  });
});
describe("US-LOG-01 AC3 safe decision log",()=>{
  it("whitelists codes and references; discards actor names, reasons and arbitrary snapshots",()=>{
    const result=decisions({total:1,items:[{
      id:7,ts:"2026-11-09T08:00:00Z",action:"ALT_SELECTED",order_id:42,actor_user_id:12,actor_role:"dispatcher",
      actor_name:"PRIVATE ACTOR",reason_text:"PRIVATE REASON",before:{phone:"PRIVATE PHONE"},
      after:{email:"PRIVATE EMAIL"},correlation_id:"6c0fd48c-c8e0-4f0d-a334-b99b79fc59e4",
    }]});
    expect(result.items[0]).toMatchObject({id:7,action:"ALT_SELECTED",subject:"Order #42",at:"2026-11-09T08:00:00Z",actor:"dispatcher · user #12"});
    expect(JSON.stringify(result)).not.toContain("PRIVATE");
    expect(result.items[0].correlationId).toBe("6c0fd48c-c8e0-4f0d-a334-b99b79fc59e4");
    expect(decisions({items:[{id:8,ts:"2026-11-09T08:00:00Z PRIVATE",actor_role:"PRIVATE",actor_user_id:123}]}).items[0])
      .toMatchObject({at:"Unavailable",actor:"User #123"});
  });
});
