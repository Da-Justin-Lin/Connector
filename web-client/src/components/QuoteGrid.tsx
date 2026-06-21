"use client";

import { useEffect, useState, type ReactNode } from "react";

import api from "@/services/api";

export interface Quote {
  symbol: string;
  last: number | null;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
}

interface QuotesResponse {
  quotes: Quote[];
  available: boolean;
  message: string | null;
}

const POLL_MS = 60_000;

type Kind = "price" | "yield";

interface QuoteGridProps {
  title: string;
  subtitle?: string;
  symbols: string[];
  labels?: Record<string, string>;
  kind?: Kind;
  heatmap?: boolean;
  sortByChange?: boolean;
  renderFooter?: (quotes: Quote[]) => ReactNode;
}

function fmtNum(n: number, digits = 2) {
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtValue(q: Quote, kind: Kind) {
  if (q.last == null) return "—";
  return kind === "yield" ? `${q.last.toFixed(2)}%` : `$${fmtNum(q.last)}`;
}

function fmtChange(q: Quote, kind: Kind) {
  if (kind === "yield") {
    if (q.change == null) return "—";
    const bps = q.change * 100; // percentage points → basis points
    return `${bps >= 0 ? "+" : "−"}${Math.abs(Math.round(bps))} bps`;
  }
  if (q.change_pct == null) return "—";
  const pct = q.change_pct * 100;
  return `${pct >= 0 ? "+" : "−"}${Math.abs(pct).toFixed(2)}%`;
}

// Background tint for heatmap tiles, scaled by day move (caps at ±3%).
function heatColor(changePct: number | null) {
  if (changePct == null) return "#f9fafb";
  const capped = Math.max(-0.03, Math.min(0.03, changePct));
  const intensity = Math.abs(capped) / 0.03; // 0..1
  const alpha = 0.08 + intensity * 0.22;
  return changePct >= 0 ? `rgba(16,185,129,${alpha})` : `rgba(239,68,68,${alpha})`;
}

export default function QuoteGrid({
  title,
  subtitle,
  symbols,
  labels = {},
  kind = "price",
  heatmap = false,
  sortByChange = false,
  renderFooter,
}: QuoteGridProps) {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const url = `/api/v1/market/quotes?symbols=${encodeURIComponent(symbols.join(","))}`;
    const load = (initial: boolean) => {
      api
        .get<QuotesResponse>(url)
        .then(({ data }) => {
          if (cancelled) return;
          setQuotes(data.quotes);
          setError(!data.available);
        })
        .catch(() => {
          if (!cancelled && initial) setError(true);
        })
        .finally(() => {
          if (!cancelled && initial) setLoading(false);
        });
    };
    load(true);
    const id = setInterval(() => load(false), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
    // symbols is a stable literal per call site
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Preserve the requested order unless we're ranking by performance.
  const ordered = sortByChange
    ? [...quotes].sort((a, b) => (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity))
    : symbols.map((s) => quotes.find((q) => q.symbol === s)).filter((q): q is Quote => !!q);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-baseline justify-between">
        <p className="text-base font-semibold text-gray-900">{title}</p>
        {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
      </div>

      {loading ? (
        <p className="mt-4 text-sm text-gray-400">Loading…</p>
      ) : error && ordered.length === 0 ? (
        <p className="mt-4 text-sm text-gray-500">Market data unavailable right now.</p>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {ordered.map((q) => {
              const up = (q.change ?? 0) >= 0;
              return (
                <div
                  key={q.symbol}
                  className="rounded-lg border border-gray-100 p-3"
                  style={heatmap ? { background: heatColor(q.change_pct) } : undefined}
                >
                  <p className="truncate text-xs font-medium text-gray-600">
                    {labels[q.symbol] ?? q.symbol}
                  </p>
                  <p className="mt-0.5 text-sm font-bold text-gray-900">{fmtValue(q, kind)}</p>
                  <p className={`text-xs font-medium ${up ? "text-emerald-600" : "text-rose-600"}`}>
                    {fmtChange(q, kind)}
                  </p>
                </div>
              );
            })}
          </div>
          {renderFooter && ordered.length > 0 && (
            <div className="mt-3 border-t border-gray-100 pt-3">{renderFooter(quotes)}</div>
          )}
        </>
      )}
    </div>
  );
}
