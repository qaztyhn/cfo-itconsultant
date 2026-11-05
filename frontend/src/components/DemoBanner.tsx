/**
 * DemoBanner — Banner 'DEMO · SYNTHETIC DATA' + câu ngữ cảnh theo màn; hiện khi APP_ENV != production.
 * Owner: Dev 3 (luồng C).
 */
export interface DemoBannerProps {
  className?: string;
}

export function DemoBanner({ className }: DemoBannerProps) {
  // TODO(#C-DemoBanner)
  return <div className={className} data-component="DemoBanner" />;
}
