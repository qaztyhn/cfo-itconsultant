/**
 * MaskedText — Che email/điện thoại theo vai trò (u•••@…, +46 •• ••• 12 34).
 * Owner: Dev 3 (luồng C).
 */
export interface MaskedTextProps {
  className?: string;
}

export function MaskedText({ className }: MaskedTextProps) {
  // TODO(#C-MaskedText)
  return <div className={className} data-component="MaskedText" />;
}
