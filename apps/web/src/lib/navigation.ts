import type { Permission } from "@/lib/api/types";

export interface NavItem {
  id: string;
  label: string;
  href: string;
  /** Permission required to view this area. Backend remains the authority. */
  permission: Permission;
}

/**
 * Terminal navigation. Each area is gated on a backend permission. Areas whose
 * backend endpoint does not exist yet are still listed so the shell is
 * navigable, but their screens render an honest "Unavailable" state — never
 * fabricated data (spec §7).
 */
export const NAV_ITEMS: readonly NavItem[] = [
  { id: "dashboard", label: "Dashboard", href: "/dashboard", permission: "system:read" },
  { id: "markets", label: "Markets", href: "/markets", permission: "trading:view" },
  { id: "watchlist", label: "Watchlist", href: "/watchlist", permission: "trading:view" },
  { id: "charts", label: "Charts", href: "/charts", permission: "trading:view" },
  { id: "orders", label: "Orders", href: "/orders", permission: "trading:view" },
  { id: "positions", label: "Positions", href: "/positions", permission: "trading:view" },
  { id: "portfolio", label: "Portfolio", href: "/portfolio", permission: "trading:view" },
  { id: "pnl", label: "P&L", href: "/pnl", permission: "trading:view" },
  { id: "strategies", label: "Strategies", href: "/strategies", permission: "trading:view" },
  { id: "risk", label: "Risk", href: "/risk", permission: "trading:view" },
  { id: "brokers", label: "Brokers", href: "/brokers", permission: "trading:view" },
  { id: "reconciliations", label: "Reconciliations", href: "/reconciliations", permission: "trading:view" },
  { id: "alerts", label: "Alerts", href: "/alerts", permission: "trading:view" },
  { id: "settings", label: "Settings", href: "/settings", permission: "system:read" },
];
