/**
 * DemoBanner — Banner 'DEMO · SYNTHETIC DATA' + câu ngữ cảnh theo màn; hiện khi APP_ENV != production (docs/03 mục 3.1).
 * Khi chạy bằng MSW (dev:mock) thêm cảnh báo: mock PASS không chứng minh tích hợp thật PASS.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { APP_ENV, USE_MOCKS, isDemoEnv } from "../api/config";

export interface DemoBannerProps {
  /** Câu ngữ cảnh theo màn, lấy từ demoContextFor(pathname). */
  context?: string;
  /** Mặc định lấy từ config; truyền vào khi test. */
  env?: string;
  mock?: boolean;
  className?: string;
}

export function DemoBanner({ context, env = APP_ENV, mock = USE_MOCKS, className }: DemoBannerProps) {
  if (!isDemoEnv(env)) {
    return null;
  }

  return (
    <div
      role="note"
      data-component="DemoBanner"
      className={["flex flex-wrap items-center gap-x-3 gap-y-1 bg-deepPine px-6 py-2", className].filter(Boolean).join(" ")}
    >
      <span className="font-mono text-overline uppercase text-apricot">DEMO · SYNTHETIC DATA</span>
      {context && <span className="text-caption text-surface">{context}</span>}
      {mock && <span className="font-mono text-caption text-apricot">Mock API · not integrated with the real backend</span>}
    </div>
  );
}