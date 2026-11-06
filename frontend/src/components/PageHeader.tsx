/**
 * PageHeader — Overline + H1 + description with optional breadcrumbs.
 * Owner: Dev 3 (luồng C).
 */
import { ChevronRight } from "lucide-react";

export interface BreadcrumbItem {
  label: string;
  href: string;
}

export interface PageHeaderProps {
  overline?: string;
  title: string;
  description?: string;
  breadcrumbs?: BreadcrumbItem[];
  className?: string;
}

export function PageHeader({ overline, title, description, breadcrumbs, className }: PageHeaderProps) {
  return (
    <header className={`flex flex-col gap-1 ${className ?? ""}`}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-[11px] font-mono text-inkMuted mb-1">
          {breadcrumbs.map((crumb, i) => (
            <span key={crumb.href} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="w-3 h-3" aria-hidden="true" />}
              <a
                href={crumb.href}
                className="hover:text-ink hover:underline transition-colors"
              >
                {crumb.label}
              </a>
            </span>
          ))}
        </nav>
      )}
      {overline && (
        <span className="text-[11px] font-mono uppercase tracking-widest text-inkMuted">
          {overline}
        </span>
      )}
      <h1 className="text-2xl font-sans font-semibold text-ink leading-tight">{title}</h1>
      {description && (
        <p className="text-sm font-sans text-inkMuted mt-0.5">{description}</p>
      )}
    </header>
  );
}
