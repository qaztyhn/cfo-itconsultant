/**
 * PageHeader — overline mono → H1 → mô tả một dòng; breadcrumb ở màn chi tiết (docs/03 mục 3.1).
 * Breadcrumb là liên kết điều hướng phía client (không tải lại trang), mục cuối là trang hiện tại.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { Link } from "react-router-dom";

export interface BreadcrumbItem {
  label: string;
  /** Đường dẫn trong SPA (vd. "/dispatcher/orders"). */
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
    <header className={["flex flex-col gap-1", className].filter(Boolean).join(" ")}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav aria-label="Breadcrumb" className="mb-1 flex items-center gap-1 font-mono text-overline text-inkMuted">
          {breadcrumbs.map((crumb, index) => (
            <span key={`${crumb.href}|${crumb.label}`} className="flex items-center gap-1">
              {index > 0 && <span aria-hidden="true">/</span>}
              <Link
                to={crumb.href}
                aria-current={index === breadcrumbs.length - 1 ? "page" : undefined}
                className="transition-colors hover:text-ink hover:underline"
              >
                {crumb.label}
              </Link>
            </span>
          ))}
        </nav>
      )}
      {overline && <span className="font-mono text-overline uppercase text-inkMuted">{overline}</span>}
      <h1 className="font-sans text-h1 text-ink">{title}</h1>
      {description && <p className="mt-0.5 font-sans text-body text-inkMuted">{description}</p>}
    </header>
  );
}
