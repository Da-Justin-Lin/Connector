"use client";

import { usePlaidLink } from "@/hooks/usePlaidLink";

export default function PlaidLinkButton() {
  const { open, ready, error } = usePlaidLink();

  return (
    <div className="flex flex-col items-end gap-1">
      {error && <p className="text-xs text-red-500">{error}</p>}
      <button
        onClick={() => open()}
        disabled={!ready}
        className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Connect Account
      </button>
    </div>
  );
}
