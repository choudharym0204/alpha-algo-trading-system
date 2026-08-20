import type { ReactNode } from "react";

/** Minimal hover/focus tooltip (title attribute plus styled marker). */
export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="group relative inline-flex" title={label}>
      {children}
    </span>
  );
}
