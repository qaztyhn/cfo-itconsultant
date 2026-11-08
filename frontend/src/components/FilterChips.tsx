/**
 * FilterChips — Row of filter chips with count badges.
 * Owner: Dev 3 (luồng C).
 */

export interface FilterOption {
  label: string;
  count?: number;
  value: string;
}

export interface FilterChipsProps {
  options: FilterOption[];
  selected: string;
  onChange: (value: string) => void;
  className?: string;
}

export function FilterChips({ options, selected, onChange, className }: FilterChipsProps) {
  return (
    <div className={`flex flex-wrap gap-2 ${className ?? ""}`} role="group" aria-label="Filter options">
      {options.map((opt) => {
        const isActive = opt.value === selected;
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control text-sm font-sans transition-colors focus:outline-none focus:ring-2 focus:ring-pine/40 ${
              isActive
                ? "bg-ink text-white"
                : "bg-chip text-ink hover:bg-border"
            }`}
            aria-pressed={isActive}
            aria-label={`${opt.label}${opt.count !== undefined ? `, ${opt.count} orders` : ""}`}
          >
            {opt.label}
            {opt.count !== undefined && (
              <span
                className={`text-[11px] font-mono px-1.5 py-0.5 rounded-full min-w-[20px] text-center ${
                  isActive ? "bg-white/20 text-white" : "bg-white/60 text-ink"
                }`}
              >
                {opt.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
