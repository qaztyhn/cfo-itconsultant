/**
 * JourneyBar — 6 đoạn Approved → Delivered; đoạn quá mốc màu apricot.
 * Owner: Dev 3 (luồng C).
 */
export interface JourneyBarProps {
  className?: string;
}

export function JourneyBar({ className }: JourneyBarProps) {
  // TODO(#C-JourneyBar)
  return <div className={className} data-component="JourneyBar" />;
}
