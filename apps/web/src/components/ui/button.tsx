import { forwardRef } from "react";

export type ButtonVariant = "primary" | "secondary" | "outline" | "danger" | "ghost";

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-accent text-black hover:bg-emerald-400 disabled:bg-accent-dim disabled:text-emerald-100/60",
  secondary: "bg-surface-raised text-white hover:bg-surface-border border border-surface-border disabled:opacity-50",
  outline: "border border-surface-border text-white hover:bg-surface-raised disabled:opacity-50",
  danger: "bg-sell text-white hover:bg-red-500 disabled:opacity-50",
  ghost: "text-muted hover:text-white hover:bg-surface-raised disabled:opacity-50",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", loading = false, disabled, className = "", children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed ${variantClasses[variant]} ${className}`}
      {...props}
    >
      {loading ? <span aria-hidden>…</span> : null}
      {children}
    </button>
  );
});
