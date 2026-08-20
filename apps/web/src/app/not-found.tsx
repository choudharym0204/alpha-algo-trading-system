import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-surface p-4 text-center">
      <p className="text-3xl font-semibold text-white">404</p>
      <p className="text-sm text-muted">This page does not exist.</p>
      <Link
        href="/dashboard"
        className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-black hover:bg-emerald-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        Go to dashboard
      </Link>
    </div>
  );
}
