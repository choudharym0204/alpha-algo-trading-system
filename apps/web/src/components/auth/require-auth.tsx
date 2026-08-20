"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/context/auth-context";
import type { Permission } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";

/**
 * Route guard. Backend authorization is the final boundary; this only prevents
 * rendering protected UI before the backend has authenticated the user. It
 * redirects unauthenticated sessions to /login and blocks missing permissions
 * with an explicit denial (server 401/403 is still handled everywhere).
 */
export function RequireAuth({
  children,
  permission,
}: {
  children: ReactNode;
  permission?: Permission;
}) {
  const { status, hasPermission } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="flex h-screen flex-col gap-3 p-6">
        <Skeleton className="h-10 w-40" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (status === "unauthenticated") {
    return null;
  }

  if (permission && !hasPermission(permission)) {
    return (
      <div className="p-6">
        <ErrorState
          title="Access denied"
          message={`You do not have the required "${permission}" permission.`}
        />
      </div>
    );
  }

  return <>{children}</>;
}
