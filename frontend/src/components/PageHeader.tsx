/**
 * PageHeader — Overline mono → H1 → mô tả một dòng; breadcrumb ở màn chi tiết.
 * Owner: Dev 3 (luồng C).
 */
export interface PageHeaderProps {
  className?: string;
}

export function PageHeader({ className }: PageHeaderProps) {
  // TODO(#C-PageHeader)
  return <div className={className} data-component="PageHeader" />;
}
