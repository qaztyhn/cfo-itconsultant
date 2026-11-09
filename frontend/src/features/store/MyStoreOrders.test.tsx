import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthUser } from "../../api/contracts/auth";
import { useAuthStore } from "../../app/store";
import { MyStoreOrders } from "./MyStoreOrders";

const SALES: AuthUser = {
  id: 21, employee_id: 21, name:"Demo Sales", roles:["sales"], market:"SE",
  location_ids:[21],locale:"en",kpi_scopes:[],
};
function session(user:AuthUser) {
  useAuthStore.getState().setAuth({
    access_token:"test-only",token_type:"bearer",expires_in:3600,user,
  },"test@synthetic.invalid");
}
const rows={items:[
  {id:301,order_no:"SE-301",status:"APPROVED",origin_store:{id:21,code:"ST-21"},
    customer_name:"Synthetic Customer",site:"Demo Site",date_request:{date_to:"2026-11-12"},
    committed_date:"2026-11-12",promise_end:"2026-11-12T12:00:00Z"},
  {id:302,order_no:"SE-302",status:"PLANNED",origin_store:{id:22,code:"ST-22"}},
],page:1,page_size:20,total:2};
type MockConfig={failList?:number;failDetail?:number;malformed?:boolean;pending?:boolean;empty?:boolean};
function api(config:MockConfig={}) {
  const calls:{method:string;url:URL}[]=[];
  vi.stubGlobal("fetch",vi.fn(async (input: RequestInfo | URL,init?:RequestInit)=>{
    const url=new URL(String(input)),method=init?.method??"GET";
    calls.push({method,url});
    if(config.pending) return new Promise<Response>(()=>{});
    if(url.pathname.endsWith("/orders")) {
      if(config.failList) return new Response(JSON.stringify({error:{code:"FORBIDDEN",message:"PRIVATE"}}),{status:config.failList});
      return Response.json(config.malformed ? {foo:"bad"} : config.empty ? {items:[],total:0} : rows);
    }
    if(url.pathname.endsWith("/orders/301")) {
      if(config.failDetail) return new Response(JSON.stringify({error:{code:"NOT_FOUND",message:"PRIVATE"}}),{status:config.failDetail});
      return Response.json({id:301,order_no:"SE-301",status:"APPROVED",origin_store:{id:21},
        date_request:{date_to:"2026-11-12"},committed:{date:"2026-11-12",promise_end:"2026-11-12T12:00:00Z"},
        risk:{forecast_eta:"2026-11-12T11:30:00Z"},contact:{phone:"PRIVATE"},
        lines:[{line_no:1,name:"Cement",qty_sale:2,sale_unit:"bag"}]});
    }
    return new Response(null,{status:404});
  }));
  return calls;
}
function mount(path="/store/orders") {
  const client=new QueryClient({defaultOptions:{queries:{retry:false,refetchOnWindowFocus:false}}});
  return render(<QueryClientProvider client={client}>
    <MemoryRouter initialEntries={[path]}><Routes>
      <Route path="/store/orders" element={<MyStoreOrders/>}/>
      <Route path="/revenue" element={<p>Revenue destination</p>}/>
    </Routes></MemoryRouter>
  </QueryClientProvider>);
}
beforeEach(()=>session(SALES));
afterEach(()=>vi.unstubAllGlobals());

describe("US-ORD-02 AC1 store-scoped list and permissions",()=>{
  it("renders allowed store only and makes GET requests",async()=>{
    const calls=api();
    mount();
    expect(await screen.findByText("SE-301")).toBeInTheDocument();
    expect(screen.queryByText("SE-302")).not.toBeInTheDocument();
    expect(calls).toHaveLength(1);
    expect(calls[0].url.searchParams.get("page_size")).toBe("20");
    expect(calls[0].url.searchParams.get("sort")).toBe("submitted_at");
    expect(calls.every(c=>c.method==="GET")).toBe(true);
    expect(screen.queryByRole("link",{name:/Revenue/})).not.toBeInTheDocument();
  });
  it("restricts direct mount without Sales role or assigned stores",async()=>{
    session({...SALES,roles:["viewer"]});
    const calls=api();mount();
    expect(screen.getByText(/Sales access required/)).toBeInTheDocument();
    await waitFor(()=>expect(calls).toHaveLength(0));
  });
  it("does not send requests when no store is assigned or URL store is unauthorized",async()=>{
    session({...SALES,location_ids:[]});
    const calls=api();mount();
    expect(screen.getByText(/No authorized store assignment/)).toBeInTheDocument();
    await waitFor(()=>expect(calls).toHaveLength(0));
  });
  it("blocks a malicious store URL instead of falling back to broader market data",async()=>{
    const calls=api();mount("/store/orders?store=22");
    expect(screen.getByRole("alert")).toHaveTextContent("Selected store is unavailable");
    await waitFor(()=>expect(calls).toHaveLength(0));
  });
  it("shows Revenue only for an assigned store owner",async()=>{
    session({...SALES,owned_location_ids:[21]});
    api();mount();
    expect(await screen.findByRole("link",{name:/Revenue · my location/})).toBeInTheDocument();
  });
});
describe("US-ORD-02 AC3 server-driven search, filter, sort and pagination",()=>{
  it("passes filters to backend and resets page on filter changes",async()=>{
    const calls=api();
    mount("/store/orders?page=2");
    await screen.findByText("SE-301");
    await userEvent.selectOptions(screen.getByRole("combobox",{name:"Status"}),"APPROVED");
    await userEvent.selectOptions(screen.getByRole("combobox",{name:"Sort"}),"promise_end");
    await userEvent.type(screen.getByRole("textbox",{name:"Search"}),"SE-301");
    await waitFor(()=>expect(calls.some(c=>c.url.searchParams.get("status")==="APPROVED"&&
      c.url.searchParams.get("sort")==="promise_end"&&c.url.searchParams.get("q")==="SE-301"&&
      c.url.searchParams.get("page")==="1")).toBe(true));
  });
  it("supports next and previous pages using backend total",async()=>{
    const calls=api();
    const many={...rows,total:45};
    // Return 45 total for paging.
    vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
      const url=new URL(String(input));calls.push({url,method:init?.method??"GET"});
      return Response.json(many);
    }));
    mount();
    await screen.findByText("SE-301");
    await userEvent.click(screen.getByRole("button",{name:"Next"}));
    await waitFor(()=>expect(calls.some(c=>c.url.searchParams.get("page")==="2")).toBe(true));
    await userEvent.click(screen.getByRole("button",{name:"Previous"}));
    await waitFor(()=>expect(calls.filter(c=>c.url.searchParams.get("page")==="1").length).toBeGreaterThan(1));
  });
});
describe("US-ORD-02 AC2 read-only detail",()=>{
  it("loads only scoped GET detail, excludes contact and GPS, and has no mutation controls",async()=>{
    const calls=api();const view=mount();
    await screen.findByText("SE-301");
    await userEvent.click(screen.getByRole("button",{name:"View details"}));
    const panel=await screen.findByRole("region",{name:/Order details/});
    expect(within(panel).getByText("Cement")).toBeInTheDocument();
    expect(within(panel).getByText(/2026-11-12 11:30 UTC/)).toBeInTheDocument();
    expect(view.container.textContent).not.toContain("PRIVATE");
    expect(calls.some(c=>c.url.pathname.endsWith("/orders/301"))).toBe(true);
    expect(calls.every(c=>c.method==="GET")).toBe(true);
    expect(screen.queryByRole("button",{name:/Confirm|Dispatch|Approve/})).not.toBeInTheDocument();
  });
  it("does not reveal unavailable or out-of-scope details on 404",async()=>{
    api({failDetail:404});mount("/store/orders?order=301");
    expect(await screen.findByText(/Order unavailable or outside your store scope/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("PRIVATE");
  });
});
describe("US-ORD-02 resilience",()=>{
  it("shows forbidden, failure and empty states without exposing server error text",async()=>{
    api({failList:403});mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("Access denied");
    expect(document.body.textContent).not.toContain("PRIVATE");
    expect(screen.getByRole("button",{name:"Retry"})).toBeInTheDocument();
  });
  it("shows an empty list when the server reports zero orders",async()=>{
    api({empty:true});mount();
    expect(await screen.findByText(/No orders returned/)).toBeInTheDocument();
  });
  it("fails closed on an invalid response instead of claiming empty store",async()=>{
    api({malformed:true});mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid order response");
  });
  it("shows loading while request is pending",()=>{
    api({pending:true});mount();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
});
