"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { dashboardNavigation } from "./navigation";

function isNavigationItemActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") {
    return pathname === href;
  }

  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function DashboardSidebar() {
  const pathname = usePathname();

  return (
    <aside className="border-b border-zinc-800 bg-zinc-950 md:flex md:min-h-screen md:w-64 md:shrink-0 md:flex-col md:border-b-0 md:border-r">
      <div className="flex items-center justify-between px-5 py-5 md:block md:px-6 md:py-7">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-3 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-white"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white text-sm font-bold text-zinc-950">
            AD
          </span>
          <span>
            <span className="block text-sm font-semibold tracking-wide text-white">
              AgentDesk
            </span>
            <span className="block text-xs text-zinc-500">
              Operations console
            </span>
          </span>
        </Link>
      </div>

      <nav
        aria-label="Dashboard navigation"
        className="flex gap-2 overflow-x-auto px-4 pb-4 md:block md:flex-1 md:space-y-1 md:overflow-visible md:px-3"
      >
        {dashboardNavigation.map((item) => {
          const active = isNavigationItemActive(pathname, item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`block min-w-max rounded-lg px-3 py-2.5 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-white md:w-full ${
                active
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              <span className="block font-medium">{item.label}</span>
              <span
                className={`mt-0.5 hidden text-xs md:block ${
                  active ? "text-zinc-400" : "text-zinc-600"
                }`}
              >
                {item.description}
              </span>
            </Link>
          );
        })}
      </nav>

      <div className="hidden border-t border-zinc-800 px-6 py-5 text-xs text-zinc-600 md:block">
        Local workspace
      </div>
    </aside>
  );
}
