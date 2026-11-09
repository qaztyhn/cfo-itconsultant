/** Conservative display-only projections. The server owns all KPI calculations. */
export const METRICS = [
  {key:"planning_time_min",label:"Planning time / order",unit:"min",direction:"lower"},
  {key:"on_time_rate",label:"On-time delivery",unit:"percent",direction:"higher"},
  {key:"labour_hours_per_delivery",label:"Labour / delivery",unit:"h",direction:"lower"},
  {key:"km_per_delivery",label:"Distance / delivery",unit:"km",direction:"lower"},
  {key:"prep_error_min",label:"Preparation error",unit:"min",direction:"lower"},
  {key:"eta_error_min",label:"ETA error",unit:"min",direction:"lower"},
  {key:"plan_acceptance_rate",label:"Plan acceptance",unit:"percent",direction:"higher"},
  {key:"failed_delivery_rate",label:"Failed deliveries",unit:"percent",direction:"lower"},
  {key:"capacity_utilisation",label:"Capacity utilisation",unit:"percent",direction:"higher"},
  {key:"manual_plan_count",label:"Manual plans",unit:"count",direction:"lower"},
] as const;
export type MetricKey = (typeof METRICS)[number]["key"];
export const CARDS: readonly MetricKey[][] = [
  ["planning_time_min"],["on_time_rate"],["labour_hours_per_delivery","km_per_delivery"],
  ["prep_error_min"],["eta_error_min"],["plan_acceptance_rate","manual_plan_count"],
  ["failed_delivery_rate"],["capacity_utilisation"],
];
export const DIAGNOSTICS = [
  {key:"hard_constraint_violations",label:"Hard-constraint violations",unit:"count"},
  {key:"event_to_alert_latency_s_median",label:"Event → alert latency (median)",unit:"s"},
] as const;
type ObjectValue=Record<string,unknown>;
function object(raw:unknown):ObjectValue{return raw !== null && typeof raw==="object" && !Array.isArray(raw)?raw as ObjectValue:{};}
function num(value:unknown):number|null{return typeof value==="number" && Number.isFinite(value)?value:null;}
function int(value:unknown):number|null{return typeof value==="number" && Number.isSafeInteger(value) && value>=0?value:null;}
export function validDate(value:string|null):string|null {
  if(!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date=Date.parse(value+"T00:00:00Z");
  return Number.isFinite(date) && new Date(date).toISOString().slice(0,10)===value?value:null;
}
export function validId(value:string|null):number|null {
  if(!value || !/^[1-9]\d*$/.test(value))return null;
  const id=Number(value);return Number.isSafeInteger(id)?id:null;
}
export function metricValue(input:unknown,key:MetricKey) {
  const data=object(object(input).metrics),entry=object(data[key]);
  return {value:num(entry.value),baseline:num(entry.baseline),change:num(entry.change)};
}
export function diagnosticValue(input:unknown,key:(typeof DIAGNOSTICS)[number]["key"]):number|null {
  return num(object(input)[key]);
}
export function displayValue(value:number|null,unit:string):string {
  if(value===null)return "Unavailable";
  const formatted=(unit==="percent"?value*100:value).toLocaleString("en-US",{maximumFractionDigits:2});
  return unit==="percent"?formatted+"%":unit==="count"?formatted:formatted+" "+unit;
}
export type Point={day:string;value:number|null};
export function dailyPoints(raw:unknown):Point[] {
  const data=object(raw),items=Array.isArray(data.points)?data.points:Array.isArray(data.items)?data.items:[];
  return items.slice(0,366).flatMap(row=>{
    const x=object(row),day=validDate(typeof x.day==="string"?x.day:null);
    return day?[{day,value:num(x.value)}]:[];
  }).sort((a,b)=>a.day.localeCompare(b.day));
}
export type SafeDecision={id:number;at:string;action:string;subject:string;actor:string;correlationId:string|null};
const CODE=/^[A-Z][A-Z0-9_]{0,63}$/;
const REF=/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
const TIMESTAMP=/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;
export function decisions(raw:unknown):{items:SafeDecision[];total:number|null} {
  const data=object(raw),list=Array.isArray(data.items)?data.items:[];
  return {total:int(data.total),items:list.slice(0,100).flatMap(entry=>{
    const x=object(entry),id=int(x.id);
    if(id===null)return [];
    // Do NOT render actor names, free-text reasons, before/after, snapshot, PII or raw JSON.
    const action=typeof x.action==="string"&&CODE.test(x.action)?x.action:"UNVERIFIED";
    const at=typeof x.created_at==="string"&&TIMESTAMP.test(x.created_at)?x.created_at:
      typeof x.at==="string"&&TIMESTAMP.test(x.at)?x.at:"Unavailable";
    const subject=typeof x.order_id==="number"&&int(x.order_id)!==null?`Order #${x.order_id}`:
      typeof x.subject_ref==="string"&&REF.test(x.subject_ref)?x.subject_ref:"Not reported";
    const correlationId=typeof x.correlation_id==="string"&&/^[a-fA-F0-9-]{36}$/.test(x.correlation_id)?x.correlation_id:null;
    return [{id,at,action,subject,actor:"Withheld for privacy",correlationId}];
  })};
}
export function pageNumber(raw:string|null):number {
  const id=validId(raw);return id===null?1:id;
}
