import type { Permission } from "@/lib/api/types";

/** Backend permission names (mirrors apps/api/.../auth.py Permissions). */
export const PERMISSIONS = {
  SYSTEM_READ: "system:read",
  TRADING_VIEW: "trading:view",
  PAPER_TRADE: "trading:paper",
  LIVE_TRADE: "trading:live",
} as const;

/**
 * Authorization is the BACKEND's boundary. This helper only drives what the UI
 * shows/hides; a server-side 401/403 is still the final authority and is
 * handled gracefully. The frontend never treats a hidden control as security.
 */
export function hasPermission(
  permissions: readonly Permission[] | null | undefined,
  required: Permission,
): boolean {
  return Boolean(permissions && permissions.includes(required));
}

export function hasAnyPermission(
  permissions: readonly Permission[] | null | undefined,
  required: readonly Permission[],
): boolean {
  return required.some((permission) => hasPermission(permissions, permission));
}
