/** Daily bars and booked line: scale only, never sum/derive authoritative financial totals. */
import type { RevenueDaily } from "./revenueApi";
import { money } from "./revenueApi";

export function RevenueChart({ data }: { data: RevenueDaily }) {
  if (data.points.length === 0) {
    return <p className="py-12 text-center text-inkMuted">No daily revenue data in this period.</p>;
  }
  const points = data.points.filter(point =>
    Number.isFinite(Number(point.recognised)) && Number.isFinite(Number(point.booked)) &&
    Number(point.recognised) >= 0 && Number(point.booked) >= 0,
  );
  if (!points.length) return <p role="status">Chart data unavailable.</p>;
  const top = Math.max(1, ...points.flatMap(p => [Number(p.recognised), Number(p.booked)]));
  const width = Math.max(640, points.length * 35), height = 230, topPad = 20, bottom = 190;
  const step = width / points.length;
  const y = (value: number) => bottom - value / top * (bottom - topPad);
  const polyline = points.map((point, index) => `${step * (index + 0.5)},${y(Number(point.booked))}`).join(" ");
  return (
    <figure className="space-y-3">
      <div className="flex flex-wrap gap-4 text-caption text-inkMuted">
        <span><span aria-hidden="true" className="mr-2 inline-block h-3 w-3 rounded-sm bg-pine" />Recognised (bars)</span>
        <span><span aria-hidden="true" className="mr-2 inline-block h-0.5 w-4 align-middle bg-apricot" />Booked not delivered (line)</span>
      </div>
      <div className="w-full overflow-x-auto" role="region" aria-label="Daily revenue chart" tabIndex={0}>
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img"
          aria-label={`Recognised daily revenue bars and booked not delivered daily line, ${data.currency}`}>
          <line x1="0" y1={bottom} x2={width} y2={bottom} stroke="currentColor" strokeOpacity="0.3" />
          {points.map((point, index) => {
            const recognised = Number(point.recognised);
            const x = step * (index + 0.5);
            return <g key={point.day}>
              <rect x={x - Math.min(13, step * 0.33)} y={y(recognised)}
                width={Math.min(26, step * 0.66)} height={bottom - y(recognised)} fill="var(--color-pine, #0F4D47)">
                <title>{point.day}: recognised {money(point.recognised, data.currency)}</title>
              </rect>
              {(index === 0 || index === points.length - 1 || index % Math.max(1, Math.ceil(points.length / 7)) === 0) &&
                <text x={x} y={bottom + 20} textAnchor="middle" fontSize="11" fill="currentColor">{point.day.slice(5)}</text>}
            </g>;
          })}
          <polyline points={polyline} fill="none" stroke="var(--color-apricot, #E07B39)" strokeWidth="2.5" />
          {points.map((point, index) => <circle key={point.day} cx={step * (index + 0.5)}
            cy={y(Number(point.booked))} r="3" fill="var(--color-apricot, #E07B39)">
            <title>{point.day}: booked {money(point.booked, data.currency)}</title>
          </circle>)}
        </svg>
      </div>
      <details className="text-body text-inkMuted">
        <summary className="cursor-pointer">Accessible daily figures</summary>
        <div className="max-h-56 overflow-auto">
          <table className="w-full text-left text-caption"><thead><tr><th scope="col">Day</th><th scope="col">Recognised</th><th scope="col">Booked</th></tr></thead>
            <tbody>{data.points.map(p => <tr key={p.day} className="border-t">
              <td>{p.day}</td><td>{money(p.recognised, data.currency)}</td><td>{money(p.booked, data.currency)}</td>
            </tr>)}</tbody></table>
        </div>
      </details>
    </figure>
  );
}
