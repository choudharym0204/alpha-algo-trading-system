"use client";

import { ErrorState } from "@/components/ui/error-state";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface p-4">
      <ErrorState
        title="An unexpected error occurred"
        message="The error has been captured. You can retry without signing out."
        action={
          <button
            onClick={reset}
            className="rounded-md border border-surface-border px-3 py-2 text-sm text-white hover:bg-surface-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            Try again
          </button>
        }
      />
    </div>
  );
}
