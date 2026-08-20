export type StatusTone = "ok" | "error" | "warn" | "idle" | "unknown";

const dotClasses: Record<StatusTone, string> = {
  ok: "bg-emerald-500",
  error: "bg-red-500",
  warn: "bg-amber-500",
  idle: "bg-slate-500",
  unknown: "bg-slate-500",
};

/**
 * Status indicator: a dot PLUS a text label. State is never communicated by
 * color alone (spec §33 — non-color-only indication).
 */
export function StatusIndicator({
  tone,
  label,
  title,
}: {
  tone: StatusTone;
  label: string;
  title?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5" title={title}>
      <span className={`h-2 w-2 rounded-full ${dotClasses[tone]}`} aria-hidden />
      <span className="text-xs text-muted">{label}</span>
    </span>
  );
}

export function toneFromStatus(status: string | null | undefined): StatusTone {
  switch (status) {
    case "ok":
    case "ready":
    case "connected":
    case "open":
      return "ok";
    case "error":
    case "closed":
      return "error";
    case "reconnecting":
    case "connecting":
      return "warn";
    default:
      return "unknown";
  }
}
