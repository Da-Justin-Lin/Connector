"use client";

import { SnapTradeReact } from "snaptrade-react";

import { useSnapTradeConnect } from "@/hooks/useSnapTradeConnect";

export default function ConnectAccountButton() {
  const { open, close, isOpen, loginLink, loading, error, onSuccess, onError } =
    useSnapTradeConnect();

  return (
    <div className="flex flex-col items-end gap-1">
      {error && <p className="text-xs text-red-500">{error}</p>}
      <button
        onClick={() => open()}
        disabled={loading}
        className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {loading ? "Loading…" : "Connect Account"}
      </button>
      <SnapTradeReact
        loginLink={loginLink ?? ""}
        isOpen={isOpen}
        close={close}
        onSuccess={onSuccess}
        onError={onError}
      />
    </div>
  );
}
