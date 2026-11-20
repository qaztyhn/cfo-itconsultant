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
type MockOptions={failure?:string;empty?:boolean;pending?:boolean;failBaseline?:boolean};
function api(options:MockOptions={}) {
  const calls:{path:string;search:URLSearchParams;method:string;body?:BodyInit|null}[]=[];
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const url=new URL(String(input)),path=url.pathname;
    calls.push({path,search:url.searchParams,method:init?.method??"GET",body:init?.body});
    if(path.includes("/kpi/baseline/")) return options.failBaseline ? new Response(JSON.stringify({error:{code:"FORBIDDEN",message:"PRIVATE"}}),{status:403}) : Response.json({metric:path.split("/").pop(),value:15});
    if(options.pending)return new Promise<Response>(()=>{});
    if(path.endsWith(options.failure??"__no_failure__"))return new Response(JSON.stringify({error:{code:"FORBIDDEN",message:"SECRET PRIVATE REASON"}}),{status:403});
    if(path.endsWith("/kpi/summary"))return Response.json(options.empty?{metrics:{},supporting:{}}:{metrics:{
      planning_time_min:{value:4.2,baseline:15,by_path:{sales:2.1,dispatcher:6}},
      on_time_rate:{value:0.94},
      plan_acceptance_rate:{value:0.81,by_path:{sales:0.88,dispatcher:0.72}},
      manual_intervention_rate:{value:0.09,baseline:0.35},
      eta_error_min:{median:14,p90:38,target:{median:20,p90:60}},
    },supporting:{order_to_commit_min:{by_path:{sales:6,dispatcher:95}},
      counter_commit_rate:{value:0.42},manual_plan_count:{value:2}}});
    if(path.endsWith("/kpi/daily"))return Response.json(options.empty?{points:[]}:{points:[
      {day:"2026-11-08",value:0.91},{day:"2026-11-09",value:0.94}]});
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
describe("US-KPI-01 AC1 five cards and trend",()=>{
  it("shows five KPI cards, path splits, supporting values and no Diagnostics request",async()=>{
    const calls=api();mount();
    expect(await screen.findByText("4.2 min")).toBeInTheDocument();
    const cards=screen.getByLabelText("Operational KPIs");
    expect(cards.querySelectorAll("[data-metric]")).toHaveLength(5);
    expect(within(cards).getByText(/Sales 2.1 min/)).toBeInTheDocument();
    expect(within(cards).getByText(/Dispatcher 72%/)).toBeInTheDocument();
    expect(within(cards).getByText(/Committed at the counter: 42%/)).toBeInTheDocument();
    expect(within(cards).getByText(/Manual plans: 2/)).toBeInTheDocument();
    expect(within(cards).getByText(/Median 14 min/)).toBeInTheDocument();
    expect(within(cards).getByText(/P90 38 min/)).toBeInTheDocument();
    expect(within(cards).getAllByText(/Baseline:/)).toHaveLength(2);
    expect(within(cards).queryByText(/Labour \/ delivery/)).not.toBeInTheDocument();
    expect(calls.every(c=>!c.path.endsWith("/kpi/diagnostics"))).toBe(true);
  });
  it("shows daily trend and switches metric via API without calculating KPI",async()=>{
    const calls=api();mount();
    expect(await screen.findByRole("img",{name:/Daily trend/})).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox",{name:"Trend metric"}),"eta_error_min");
    await waitFor(()=>expect(calls.some(c=>c.path.endsWith("/kpi/daily")&&c.search.get("metric")==="eta_error_min")).toBe(true));
  });
  it("shows empty daily and audit states without synthesized points",async()=>{
    api({empty:true});mount();
    expect((await screen.findAllByText(/Chưa có dữ liệu/)).length).toBeGreaterThan(0);
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
  it("saves approved baseline through admin-only PUT and refreshes server KPI",async()=>{
    signIn({...OPS,roles:["admin"],kpi_scopes:[]});
    const calls=api();mount();
    await screen.findByText("4.2 min");
    await userEvent.type(screen.getByRole("spinbutton",{name:"Baseline value"}),"15");
    await userEvent.click(screen.getByRole("button",{name:"Save baseline"}));
    expect(await screen.findByText(/Baseline saved by server/)).toBeInTheDocument();
    expect(calls.some(c=>c.path.endsWith("/kpi/baseline/planning_time_min")&&c.method==="PUT"&&c.body===JSON.stringify({value:15}))).toBe(true);
  });
  it("never claims admin baseline save when server denies action",async()=>{
    signIn({...OPS,roles:["admin"],kpi_scopes:[]});
    api({failBaseline:true});mount();
    await screen.findByText("4.2 min");
    expect(screen.getByRole("button",{name:"Save baseline"})).toBeDisabled();
    await userEvent.type(screen.getByRole("spinbutton",{name:"Baseline value"}),"15");
    await userEvent.click(screen.getByRole("button",{name:"Save baseline"}));
    expect(await screen.findByText(/Baseline was not saved/)).toBeInTheDocument();
    expect(screen.queryByText(/Baseline saved by server/)).not.toBeInTheDocument();
  });
  it("hides baseline mutation controls from non-admin ops viewers",async()=>{
    api();mount();
    await screen.findByText("4.2 min");
    expect(screen.queryByRole("button",{name:"Save baseline"})).not.toBeInTheDocument();
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
