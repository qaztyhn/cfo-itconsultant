import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthUser } from "../../api/contracts/auth";
import { useAuthStore } from "../../app/store";
import { Exceptions } from "./Exceptions";

const DISPATCHER: AuthUser = {
  id: 11, employee_id: 11, name:"Demo dispatcher", roles:["dispatcher"],
  market:"SE",location_ids:[],locale:"en",kpi_scopes:[],
};
function signIn(user:AuthUser) {
  useAuthStore.getState().setAuth({access_token:"synthetic",token_type:"bearer",expires_in:3600,user},"demo@synthetic.invalid");
}
const failures={items:[{id:31,order_no:"SE-31",status:"NO_FEASIBLE_DATE",latest_run_id:88,
  date_request:{mode:"latest",date_to:"2026-11-13"},block_reason:"STOCK_SHORT",risk:{status:"AT_RISK"}}]};
const blocked={items:[{id:41,order_no:"SE-41",status:"BLOCKED_UNMAPPED_SKU",block_reason:"SKU_UNMAPPED"}]};
const alerts={items:[{id:51,order_id:31,type:"REPLAN_SUGGESTED",resolved:false,level:"HIGH",details:{run_id:89}}]};
function apiMock(options:{fail?:boolean;unavailable?:boolean}={}) {
  const calls:string[]=[];
  vi.stubGlobal("fetch",vi.fn(async (input:RequestInfo|URL)=>{
    const url=new URL(String(input)),path=url.pathname;
    calls.push(path+url.search);
    if(options.fail) return new Response(JSON.stringify({error:{message:"PRIVATE PHONE",code:"INTERNAL_ERROR"}}),{status:503});
    if(options.unavailable) return new Promise<Response>(()=>{});
    let data:unknown={items:[]};
    if(path.endsWith("/orders")) data=url.searchParams.get("status")==="BLOCKED_UNMAPPED_SKU"?blocked:failures;
    if(path.endsWith("/alerts")) data=alerts;
    if(path.endsWith("/planning-runs/88")) data={result:"infeasible",failed_check:"stock",earliest_feasible_date:null,
      dates_searched:[{date:"2026-11-09",result:"FAIL",check:"STOCK"}],
      per_warehouse_checks:[{warehouse:"STO",stock:{passed:false,code:"STOCK_SHORT"}}]};
    if(path.endsWith("/planning-runs/89")) data={kind:"replan_suggestion",result:"feasible",hold_expires_at:null};
    if(path.endsWith("/orders/41")) data={lines:[{local_sku:"SE-SKU-41",mapping_status:"PENDING",name:"PRIVATE"}]};
    return Response.json(data);
  }));
  return calls;
}
function renderScreen(url="/dispatcher/exceptions") {
  const client=new QueryClient({defaultOptions:{queries:{retry:false,refetchOnWindowFocus:false}}});
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}>
    <Routes><Route path="/dispatcher/exceptions" element={<Exceptions/>}/></Routes>
  </MemoryRouter></QueryClientProvider>);
}
beforeEach(()=>signIn(DISPATCHER));
afterEach(()=>vi.unstubAllGlobals());

describe("US-PLN-07 AC1 / US-APR-04 AC1: exception tabs",()=>{
  it("loads infeasible orders and server evidence, without inventing a date",async()=>{
    const calls=apiMock();
    renderScreen();
    expect(await screen.findByText("SE-31")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button",{name:"Inspect infeasibility"}));
    expect(await screen.findByText(/STOCK_SHORT/,{selector:"li"})).toBeInTheDocument();
    expect(screen.getByText(/Earliest feasible date:/)).toHaveTextContent("Not verified");
    expect(calls.some(x=>x.includes("/planning-runs/88"))).toBe(true);
    expect(calls.every(x=>!x.includes("/approve")&&!x.includes("/extend")&&!x.includes("/plan?"))).toBe(true);
  });
  it("preserves URL tab and search, and filters loaded results",async()=>{
    apiMock();
    renderScreen("/dispatcher/exceptions?tab=no-feasible&q=nomatch&other=keep");
    expect(await screen.findByText(/No loaded exceptions match this filter/)).toBeInTheDocument();
    const search=screen.getByRole("textbox",{name:/Search order reference/});
    await userEvent.clear(search);
    await userEvent.type(search,"SE-31");
    expect(await screen.findByText("SE-31")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button",{name:"Replan Suggested"}));
    expect(await screen.findByText("Order #31")).toBeInTheDocument();
    expect((search as HTMLInputElement).value).toBe("SE-31");
  });
  it("shows suggestion without replacing committed plan or exposing approval",async()=>{
    const calls=apiMock();
    renderScreen("/dispatcher/exceptions?tab=replan");
    expect(await screen.findByText("Order #31")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button",{name:"Inspect suggestion"}));
    expect(await screen.findByText(/The committed plan remains in force/)).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:/Approve|Keep current/i})).not.toBeInTheDocument();
    expect(calls.every(x=>!x.includes("approve")&&!x.includes("keep-current"))).toBe(true);
  });
  it("labels blocked orders legacy and only renders safe scoped SKU data",async()=>{
    apiMock();const {container}=renderScreen("/dispatcher/exceptions?tab=blocked");
    expect(await screen.findByText("SE-41")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button",{name:"Inspect mapped SKU evidence"}));
    const panel=await screen.findByRole("region",{name:"Exception evidence"});
    expect(within(panel).getByText(/SE-SKU-41/)).toBeInTheDocument();
    expect(container.textContent).not.toContain("PRIVATE");
    expect(screen.getByText(/Only IT can map SKUs/)).toBeInTheDocument();
  });
  it("enforces role gate before any API reads",async()=>{
    signIn({...DISPATCHER,id:12,roles:["viewer"]});
    const calls=apiMock();renderScreen();
    expect(screen.getByText(/Dispatcher access required/)).toBeInTheDocument();
    await waitFor(()=>expect(calls).toHaveLength(0));
  });
  it("handles API failure without displaying untrusted server PII",async()=>{
    apiMock({fail:true});renderScreen();
    expect(await screen.findByRole("alert")).toHaveTextContent("Exception data unavailable");
    expect(document.body.textContent).not.toContain("PRIVATE PHONE");
    expect(screen.getByRole("button",{name:"Retry"})).toBeInTheDocument();
  });
  it("shows loading state when endpoint is pending",()=>{
    apiMock({unavailable:true});renderScreen();
    expect(screen.getByRole("status",{name:""})).toBeInTheDocument();
  });
});
