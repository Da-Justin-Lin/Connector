"use client";

import { togglePrivacy, usePrivacy } from "@/hooks/usePrivacy";

/** Sleek eye toggle that blurs/unblurs sensitive balances across the dashboard. */
export default function BalanceToggle({ className = "" }: { className?: string }) {
  const hidden = usePrivacy();
  return (
    <button
      type="button"
      onClick={togglePrivacy}
      aria-label={hidden ? "Show balances" : "Hide balances"}
      title={hidden ? "Show balances" : "Hide balances"}
      className={`tap grid h-9 w-9 place-items-center rounded-full border border-line/70 bg-surface/60 text-muted transition-colors hover:border-line hover:text-content ${className}`}
    >
      {hidden ? <EyeOffIcon /> : <EyeIcon />}
    </button>
  );
}

function EyeIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c6.5 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
      <path d="M6.61 6.61A13.5 13.5 0 0 0 2 12s3.5 7 10 7a9.12 9.12 0 0 0 5.39-1.61" />
      <line x1="2" y1="2" x2="22" y2="22" />
    </svg>
  );
}
