"use client";

import { RequireAuth } from "@/components/auth/require-auth";
import { AppShell } from "@/components/shell/app-shell";
import { PERMISSIONS } from "@/lib/auth/permissions";

export default function ProtectedLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth permission={PERMISSIONS.SYSTEM_READ}>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  );
}
