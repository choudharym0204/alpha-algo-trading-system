import { forwardRef, useId } from "react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string | null;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, id, className = "", ...props },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return (
    <div className="flex flex-col gap-1">
      {label ? (
        <label htmlFor={inputId} className="text-sm text-muted">
          {label}
        </label>
      ) : null}
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        className={`rounded-md border border-surface-border bg-surface-raised px-3 py-2 text-sm text-white placeholder:text-muted focus:outline focus:outline-2 focus:outline-accent ${error ? "border-sell" : ""} ${className}`}
        {...props}
      />
      {error ? (
        <p role="alert" className="text-xs text-sell">
          {error}
        </p>
      ) : null}
    </div>
  );
});
