import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {render,screen,within,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter,Routes,Route} from "react-router-dom";
import {beforeEach,afterEach,describe,it,expect,vi} from "vitest";
import type {AuthUser} from "../../api/contracts/auth";
import {useAuthStore} from "../../app/store";
import {KpiDashboard} from "./KpiDashboard";

const OPS:AuthUser={id:10,employee_id:null,name:"Demo ops",roles:["viewer"],market:"SE",
  location_ids:[],locale:"en",kpi_scopes:["ops"]};
function signIn(user:AuthUser) {useAuthStore.getState().setAuth({access_token:"synthetic",token_type:"bearer",expires_in:3600,user},"unit@synthetic.invalid");}
type MockOptions={failure?:string;empty?:boolean;pending?:boolean;nullDiagnostics?:boolean};
function api(options:MockOptions={}) {
  const calls:{path:string;search:URLSearchParams;method:string}[]=[];
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const url=new URL(String(input)),path=url.pathname;
    calls.push({path,search:url.searchParams,method:init?.method??"GET"});
    if(options.pending)return new Promise<Response>(()=>{});
    if(path.endsWith(options.failure??"__no_failure__"))return new Response(JSON.stringify({error:{code:"FORBIDDEN",message:"SECRET PRIVATE REASON"}}),{status:403});
    if(path.endsWith("/kpi/summary"))return Response.json(options.empty?{metrics:{}}:{metrics:{
      planning_time_min:{value:4.2,baseline:15,change:-10.8},
      on_time_rate:{value:0.94},labour_hours_per_delivery:{value:9.8},
      km_per_delivery:{value:31.4},prep_error_min:{value:11},
      eta_error_min:{value:14},plan_acceptance_rate:{value:0.81},
      manual_plan_count:{value:2},failed_delivery_rate:{value:0.03},
      capacity_utilisation:{value:0.71},
    }});
    if(path.endsWith("/kpi/daily"))return Response.json(options.empty?{points:[]}:{points:[
      {day:"2026-11-08",value:0.91},{day:"2026-11-09",value:0.94}]});
    if(path.endsWith("/kpi/diagnostics"))return Response.json({
      hard_constraint_violations:options.nullDiagnostics?null:0,event_to_alert_latency_s_median:null,
    });
    if(path.endsWith("/audit/decisions"))return Response.json(options.empty?{items:[],total:0}:{items:[
      {id:13,created_at:"2026-11-09T10:00:00Z",action:"ALT_SELECTED",order_id:42,
        actor_name:"PRIVATE ACTOR",reason_text:"PRIVATE REASON",snapshot:{phone:"PRIVATE PHONE"}},
    ],total:1});
    return new Response(null,{status:404});
  }));
  return calls;
}
function mount(url="/kpi") {
  const client=new QueryClient({defaultOptions:{queries:{retry:false,refetchOnWindowFocus:false}}});
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}>
    <Routes><Route path="/kpi" element={<KpiDashboard/>}/></Routes>
  </MemoryRouter></QueryClientProvider>);
}
beforeEach(()=>signIn(OPS));
afterEach(()=>vi.unstubAllGlobals());
describe("US-KPI-01 AC1 cards, trend and diagnostics",()=>{
  it("shows eight server-authoritative KPI cards and verified baseline without revenue",async()=>{
    const calls=api();mount();
    expect(await screen.findByText("4.2 min")).toBeInTheDocument();
    const cards=screen.getByLabelText("Operational KPIs");
    expect(within(cards).getAllByText(/Baseline:/)).toHaveLength(10);
    expect(within(cards).getAllByText("Unavailable")).toHaveLength(9);
    expect(within(cards).getByText("15 min",{exact:false})).toBeInTheDocument();
    expect(screen.queryByText(/profit|revenue/i)).not.toBeInTheDocument();
    expect(calls.every(c=>c.method==="GET")).toBe(true);
  });
  it("shows daily trend and switches metric via API without calculating KPI",async()=>{
    const calls=api();mount();
    expect(await screen.findByRole("img",{name:/Daily trend/})).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox",{name:"Trend metric"}),"eta_error_min");
    await waitFor(()=>expect(calls.some(c=>c.path.endsWith("/kpi/daily")&&c.search.get("metric")==="eta_error_min")).toBe(true));
  });
  it("shows null diagnostics as unavailable and never promotes unknown to zero",async()=>{
    api({nullDiagnostics:true});mount();
    const item=await screen.findByText("Hard-constraint violations");
    expect(item.closest("[data-diagnostic]")).toHaveTextContent("Unavailable");
    expect(screen.getByText("Event → alert latency (median)").closest("[data-diagnostic]")).toHaveTextContent("Unavailable");
  });
  it("shows empty daily and audit states without synthesized points",async()=>{
    api({empty:true});mount();
    expect(await screen.findByText(/No verified daily KPI points/)).toBeInTheDocument();
    expect(await screen.findByText(/No decisions reported/)).toBeInTheDocument();
  });
});
describe("US-KPI-01 AC4 admin/ops permissions and API errors",()=>{
  it("denies Business owner with revenue_all before any network request",async()=>{
    signIn({...OPS,kpi_scopes:["revenue_all"]});
    const calls=api();mount();
    expect(screen.getByText(/You do not have access to KPIs/)).toBeInTheDocument();
    await waitFor(()=>expect(calls).toHaveLength(0));
  });
  it("allows admin to request KPI and audit",async()=>{
    signIn({...OPS,roles:["admin"],kpi_scopes:[]});
    const calls=api();mount();
    await screen.findByText("4.2 min");
    await waitFor(()=>expect(calls.some(c=>c.path.endsWith("/audit/decisions"))).toBe(true));
  });
  it("does not fetch audit log for warehouse ops even though KPI cards are accessible",async()=>{
    signIn({...OPS,roles:["warehouse"],kpi_scopes:["ops"]});
    const calls=api();mount();
    expect(await screen.findByText("4.2 min")).toBeInTheDocument();
    expect(screen.getByText(/Decision log access requires/)).toBeInTheDocument();
    expect(calls.every(c=>!c.path.endsWith("/audit/decisions"))).toBe(true);
  });
  it("displays permission denial from server without echoing sensitive error content",async()=>{
    api({failure:"/kpi/summary"});mount();
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("SECRET PRIVATE REASON");
  });
  it("blocks malformed date and unauthorized location filters before requests",async()=>{
    const calls=api();mount("/kpi?from=2026-13-40&warehouse_id=3");
    expect(screen.getByText(/Invalid or unauthorised filters/)).toBeInTheDocument();
    await waitFor(()=>expect(calls).toHaveLength(0));
  });
  it("shows skeletons for pending requests",()=>{
    api({pending:true});mount();
    expect(screen.getAllByText("Loading…").length).toBeGreaterThan(0);
  });
});
describe("US-LOG-01 privacy and audit filters",()=>{
  it("forwards server filters and keeps free-text/actor data invisible",async()=>{
    const calls=api();mount();
    expect(await screen.findByText("ALT_SELECTED")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("PRIVATE");
    await userEvent.type(screen.getByRole("textbox",{name:"Order ID"}),"42");
    await userEvent.type(screen.getByRole("textbox",{name:"Action code"}),"ALT_SELECTED");
    await waitFor(()=>expect(calls.some(c=>c.path.endsWith("/audit/decisions")&&
      c.search.get("order_id")==="42"&&c.search.get("action")==="ALT_SELECTED")).toBe(true));
  });
  it("uses the same date range for summary, daily and audit",async()=>{
    const calls=api();mount("/kpi?from=2026-11-01&to=2026-11-09");
    await screen.findByText("4.2 min");
    await waitFor(()=>expect(calls.filter(c=>["/kpi/summary","/kpi/daily","/audit/decisions"].some(x=>c.path.endsWith(x)))
      .every(c=>c.search.get("from")==="2026-11-01"&&c.search.get("to")==="2026-11-09")).toBe(true));
  });
});
