"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import ThemeToggle from "@/components/ThemeToggle";
import { logout } from "@/services/authService";

const NAV_LINKS = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/deposits", label: "Deposits" },
  { href: "/dashboard/reports", label: "Reports" },
  { href: "/dashboard/macro", label: "Macro" },
];

export default function Navbar() {
  const pathname = usePathname();

  return (
    <nav className="sticky top-0 z-30 border-b border-line/70 bg-surface/70 backdrop-blur-xl">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <Link href="/dashboard" className="flex items-center gap-2 text-xl font-bold">
            <img src="/icon.svg" alt="" className="h-7 w-7" />
            <span className="bg-brand bg-clip-text text-transparent">Connector</span>
          </Link>

          <div className="flex items-center gap-1 sm:gap-2">
            {NAV_LINKS.map(({ href, label }) => {
              const active = pathname === href;
              return (
                <Link
                  key={href}
                  href={href}
                  className={`relative rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                    active ? "text-content" : "text-muted hover:text-content"
                  }`}
                >
                  {active && (
                    <span className="absolute inset-0 -z-10 rounded-full bg-brand/10" />
                  )}
                  {label}
                </Link>
              );
            })}

            <span className="mx-1 hidden h-5 w-px bg-line sm:block" />

            <ThemeToggle />

            <button
              onClick={logout}
              className="rounded-full px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:text-content"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
