"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import Navbar from "@/components/Navbar";
import { isLoggedIn, refreshSession } from "@/services/authService";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      // Fast path: we already hold an access token. Otherwise try the refresh
      // cookie so a returning user with a valid 30-day session stays logged in
      // even after the short-lived access token has expired.
      if (isLoggedIn() || (await refreshSession())) {
        if (active) setChecking(false);
      } else if (active) {
        router.replace("/login");
      }
    })();
    return () => {
      active = false;
    };
  }, [router]);

  if (checking) return null;

  return (
    <div className="min-h-screen">
      <Navbar />
      <main key={pathname} className="mx-auto max-w-7xl animate-fade-in px-4 py-8 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}
