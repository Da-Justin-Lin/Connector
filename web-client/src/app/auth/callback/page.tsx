"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect } from "react";

import { refreshSession } from "@/services/authService";

function CallbackHandler() {
  const router = useRouter();

  useEffect(() => {
    // Google's callback set the refresh cookie; exchange it for an access token.
    refreshSession().then((ok) => router.replace(ok ? "/dashboard" : "/login"));
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-2">
      <p className="text-muted">Signing you in…</p>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense>
      <CallbackHandler />
    </Suspense>
  );
}
