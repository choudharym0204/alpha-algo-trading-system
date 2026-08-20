import type { ReactNode } from "react";

/** Explicit error state with an action — never a raw stack trace (spec §29/§30). */
export function ErrorState({
  title = "Something went wrong",
  message,
  action,
}: {
  title?: string;
  message?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 px-6 py-12 text-center">
      <p className="text-sm font-medium text-white">{title}</p>
      {message ? <p className="max-w-md text-sm text-muted">{message}</p> : null}
      {action}
    </div>
  );
}
