import {describe,it,expect} from "vitest";
import {CARDS, METRICS, dailyPoints, decisions, diagnosticValue, displayValue, metricValue, validDate} from "./model";
describe("US-KPI-01 AC1 eight cards and approved metric keys",()=>{
  it("renders eight cards covering exactly the ten approved server keys",()=>{
    expect(CARDS).toHaveLength(8);
    expect(CARDS.flat().sort()).toEqual(METRICS.map(m=>m.key).sort());
  });
  it("shows missing metrics and baselines as unavailable, never zero",()=>{
    expect(metricValue({metrics:{planning_time_min:{value:4.2,baseline:15}}},"planning_time_min"))
      .toEqual({value:4.2,baseline:15,change:null});
    expect(displayValue(null,"percent")).toBe("Unavailable");
    expect(metricValue({metrics:{on_time_rate:{value:null}}},"on_time_rate").value).toBeNull();
    expect(displayValue(0,"percent")).toBe("0%");
  });
  it("keeps approved diagnostic null values unknown, without inferring zeros",()=>{
    expect(diagnosticValue({hard_constraint_violations:null},"hard_constraint_violations")).toBeNull();
    expect(diagnosticValue({hard_constraint_violations:0},"hard_constraint_violations")).toBe(0);
    expect(diagnosticValue({},"event_to_alert_latency_s_median")).toBeNull();
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
      id:7,created_at:"2026-11-09T08:00:00Z",action:"ALT_SELECTED",order_id:42,
      actor_name:"PRIVATE ACTOR",reason_text:"PRIVATE REASON",before:{phone:"PRIVATE PHONE"},
      after:{email:"PRIVATE EMAIL"},correlation_id:"6c0fd48c-c8e0-4f0d-a334-b99b79fc59e4",
    }]});
    expect(result.items[0]).toMatchObject({id:7,action:"ALT_SELECTED",subject:"Order #42"});
    expect(JSON.stringify(result)).not.toContain("PRIVATE");
    expect(result.items[0].correlationId).toBe("6c0fd48c-c8e0-4f0d-a334-b99b79fc59e4");
  });
});
