/** Khung một khối trong màn chi tiết CS: tiêu đề h3 + nội dung, có aria-labelledby. */
import { useId, type ReactNode } from "react";

export function CsSection({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h3 id={id} className="text-h3 text-ink">
        {title}
      </h3>
      {children}
    </section>
  );
}