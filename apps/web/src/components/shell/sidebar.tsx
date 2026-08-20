"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { NAV_ITEMS } from "@/lib/navigation";

export function Sidebar() {
  const pathname = usePathname();
  const { hasPermission } = useAuth();

  const visible = NAV_ITEMS.filter((item) => hasPermission(item.permission));

  return (
    <nav aria-label="Primary" className="flex w-56 shrink-0 flex-col border-r border-surface-border bg-surface">
      <div className="border-b border-surface-border px-4 py-4">
        <p className="text-sm font-semibold text-white">Alpha Algo</p>
        <p className="text-xs text-muted">Trading Terminal</p>
      </div>
      <ul className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {visible.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <li key={item.id}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${
                  active ? "bg-surface-raised text-white" : "text-muted hover:bg-surface-raised hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
