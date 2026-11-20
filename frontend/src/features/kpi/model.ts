/** Conservative display-only projections. The server owns all KPI calculations. */
export const METRICS = [
  {key:"planning_time_min",label:"Planning time / order",unit:"min",direction:"lower"},
  {key:"on_time_rate",label:"On-time delivery",unit:"percent",direction:"higher"},
  {key:"plan_acceptance_rate",label:"Plan acceptance",unit:"percent",direction:"higher"},
  {key:"manual_intervention_rate",label:"Manual interventions / order",unit:"percent",direction:"lower"},
  {key:"eta_error_min",label:"ETA error",unit:"min",direction:"lower"},
] as const;
export type MetricKey = (typeof METRICS)[number]["key"];
export const CARDS: readonly MetricKey[][] = METRICS.map(item=>[item.key]);
export const BASELINE_METRICS = METRICS.filter(item=>
  item.key==="planning_time_min" || item.key==="manual_intervention_rate");
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
  const byPath=object(entry.by_path),target=object(entry.target);
  return {value:num(entry.value),baseline:num(entry.baseline),change:num(entry.change),
    sales:num(byPath.sales),dispatcher:num(byPath.dispatcher),
    median:num(entry.median),p90:num(entry.p90),
    targetMedian:num(target.median),targetP90:num(target.p90)};
}
export function supportingValue(input:unknown,key:"order_to_commit_min"|"counter_commit_rate"|"manual_plan_count") {
  const item=object(object(input).supporting)[key],entry=object(item),byPath=object(entry.by_path);
  return {value:num(entry.value),sales:num(byPath.sales),dispatcher:num(byPath.dispatcher)};
}
export function displayValue(value:number|null,unit:string):string {
  if(value===null)return "Chưa có dữ liệu";
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
const TIMESTAMP=/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
export function decisions(raw:unknown):{items:SafeDecision[];total:number|null} {
  const data=object(raw),list=Array.isArray(data.items)?data.items:[];
  return {total:int(data.total),items:list.slice(0,100).flatMap(entry=>{
    const x=object(entry),id=int(x.id);
    if(id===null)return [];
    // Do NOT render actor names, free-text reasons, before/after, snapshot, PII or raw JSON.
    const action=typeof x.action==="string"&&CODE.test(x.action)?x.action:"UNVERIFIED";
    const at=[x.ts,x.created_at,x.at].find(value=>
      typeof value==="string"&&TIMESTAMP.test(value)&&Number.isFinite(Date.parse(value))) as string|undefined;
    const subject=typeof x.order_id==="number"&&int(x.order_id)!==null?`Order #${x.order_id}`:
      "Not reported";
    const correlationId=typeof x.correlation_id==="string"&&
      /^[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}$/.test(x.correlation_id)?x.correlation_id:null;
    const actorId=int(x.actor_user_id);
    const role=typeof x.actor_role==="string"&&
      ["admin","dispatcher","warehouse","sales","driver","customer_service","viewer"].includes(x.actor_role)
      ?x.actor_role:null;
    const actor=role?(actorId!==null?`${role} · user #${actorId}`:role):
      actorId!==null?`User #${actorId}`:"Withheld for privacy";
    return [{id,at:at??"Unavailable",action,subject,actor,correlationId}];
  })};
}
export function pageNumber(raw:string|null):number {
  const id=validId(raw);return id===null?1:id;
}
