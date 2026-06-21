"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import AccountFilter from "@/components/AccountFilter";
import api from "@/services/api";

interface TradeRow {
  trade_date: string;
  symbol: string | null;
  description: string | null;
  action: string;
  units: number;
  price: number;
  amount: number;
  asset_type?: string;
  instrument_key?: string | null;
}

interface InstrumentPnL {
  symbol: string | null;
  description: string | null;
  asset_type: string;
  buy_units: number;
  sell_units: number;
  realized_pnl: number;
  unrealized_pnl: number;
  net_units: number;
  status: string;
  needs_basis: boolean;
  needs_price: boolean;
}

interface WeeklyReport {
  week_start: string;
  week_end: string;
  trades: TradeRow[];
  total_buys: number;
  total_sells: number;
  net_cash_flow: number;
  week_start_value: number | null;
  week_end_value: number | null;
  week_deposits: number;
  week_pnl: number | null;
  week_pnl_pct: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  trading_pnl: number | null;
  pnl_by_instrument: InstrumentPnL[];
  available: boolean;
  message: string | null;
  stale?: boolean;
  last_synced_at?: string | null;
}

function fmt(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(rate: number | null | undefined) {
  if (rate == null) return "—";
  const pct = rate * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function fmtDate(iso: string) {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function fmtDateLong(iso: string) {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

// In-memory stale-while-revalidate cache, keyed by account + week window.
// Persists across navigation within the session so revisiting a week renders
// instantly while a fresh copy is fetched in the background.
const reportCache = new Map<string, WeeklyReport>();
const cacheKey = (account: string | null, start: string, end: string) =>
  `${account ?? "ALL"}|${start}|${end}`;

function StatCard({
  label,
  value,
  tone = "default",
  hint,
}: {
  label: string;
  value: string;
  tone?: "default" | "up" | "down";
  hint?: string;
}) {
  const valueColor =
    tone === "up" ? "text-emerald-600" : tone === "down" ? "text-rose-600" : "text-gray-900";
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${valueColor}`}>{value}</p>
      {hint && <p className={`mt-0.5 text-xs ${valueColor}`}>{hint}</p>}
    </div>
  );
}

export default function ReportsPage() {
  const today = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

  // weekOffset = 0 → current 7-day window ending today.
  // weekOffset = -1 → previous week (ends 7 days ago), etc.
  const [weekOffset, setWeekOffset] = useState(0);

  const { startDate, endDate } = useMemo(() => {
    const end = new Date(today);
    end.setDate(end.getDate() + weekOffset * 7);
    const start = new Date(end);
    start.setDate(start.getDate() - 6); // inclusive 7-day window
    return { startDate: isoDate(start), endDate: isoDate(end) };
  }, [today, weekOffset]);

  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [data, setData] = useState<WeeklyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [revalidating, setRevalidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Bumped to re-fetch after the server reports `stale` (a background refresh
  // is in flight); capped per window so we don't poll forever.
  const [refreshTick, setRefreshTick] = useState(0);
  const staleAttempts = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    const key = cacheKey(selectedAccountId, startDate, endDate);
    const cached = reportCache.get(key);

    // Show cached data immediately; only block with a spinner on a cold cache.
    if (cached) {
      setData(cached);
      setLoading(false);
    } else {
      setData(null);
      setLoading(true);
    }
    setRevalidating(true);
    setError(null);

    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const acct = selectedAccountId ? `&account_id=${selectedAccountId}` : "";
    api
      .get<WeeklyReport>(
        `/api/v1/reports/weekly-trades?start_date=${startDate}&end_date=${endDate}${acct}`,
      )
      .then(({ data }) => {
        reportCache.set(key, data);
        if (cancelled) return;
        setData(data);
        // If the server is refreshing in the background, pull the fresh copy
        // once it should be ready (up to a few attempts per window).
        if (data.stale) {
          const tries = staleAttempts.current.get(key) ?? 0;
          if (tries < 3) {
            staleAttempts.current.set(key, tries + 1);
            retryTimer = setTimeout(() => setRefreshTick((t) => t + 1), 3000);
          }
        } else {
          staleAttempts.current.delete(key);
        }
      })
      .catch(() => {
        if (!cancelled && !cached) setError("Failed to load report.");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setRevalidating(false);
        }
      });

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [startDate, endDate, selectedAccountId, refreshTick]);

  const pnlTone =
    data?.week_pnl == null ? "default" : data.week_pnl >= 0 ? "up" : "down";
  const tradeTone =
    data?.trading_pnl == null ? "default" : data.trading_pnl >= 0 ? "up" : "down";

  const signed = (n: number | null | undefined) =>
    n == null ? "—" : `${n >= 0 ? "+" : "−"}$${fmt(Math.abs(n))}`;

  const canGoNext = weekOffset < 0;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900">Weekly Report</h1>
            {(revalidating || data?.stale) && data && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">
                <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
                Updating…
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500">
            {fmtDateLong(startDate)} – {fmtDateLong(endDate)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <AccountFilter value={selectedAccountId} onChange={setSelectedAccountId} />
          <button
            onClick={() => setWeekOffset((w) => w - 1)}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            ← Previous
          </button>
          <button
            onClick={() => setWeekOffset(0)}
            disabled={weekOffset === 0}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            This week
          </button>
          <button
            onClick={() => setWeekOffset((w) => w + 1)}
            disabled={!canGoNext}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Next →
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-rose-500">{error}</p>}

      {loading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : data ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Trading P/L (this week's trades)"
              value={signed(data.trading_pnl)}
              tone={tradeTone}
            />
            <StatCard
              label="Realized"
              value={signed(data.realized_pnl)}
              tone={
                data.realized_pnl == null
                  ? "default"
                  : data.realized_pnl >= 0
                  ? "up"
                  : "down"
              }
            />
            <StatCard
              label="Unrealized (open positions)"
              value={signed(data.unrealized_pnl)}
              tone={
                data.unrealized_pnl == null
                  ? "default"
                  : data.unrealized_pnl >= 0
                  ? "up"
                  : "down"
              }
            />
            <StatCard
              label="Portfolio P/L (all holdings)"
              value={data.week_pnl == null ? "—" : `$${fmt(data.week_pnl)}`}
              tone={pnlTone}
              hint={fmtPct(data.week_pnl_pct)}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Total Buys" value={`$${fmt(data.total_buys)}`} />
            <StatCard label="Total Sells" value={`$${fmt(data.total_sells)}`} />
            <StatCard
              label="End of week value"
              value={data.week_end_value == null ? "—" : `$${fmt(data.week_end_value)}`}
            />
            <StatCard label="Deposits this week" value={`$${fmt(data.week_deposits)}`} />
          </div>

          {data.pnl_by_instrument.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-200 bg-gray-50 px-6 py-4">
                <p className="text-base font-semibold text-gray-900">
                  P/L by position
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  Buys and sells matched per instrument (FIFO). Open lots are
                  marked to the current price.
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-white">
                    <tr>
                      {["Symbol", "Status", "Realized", "Unrealized", "Total"].map(
                        (h) => (
                          <th
                            key={h}
                            className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500"
                          >
                            {h}
                          </th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {data.pnl_by_instrument.map((p, i) => {
                      const total = p.realized_pnl + p.unrealized_pnl;
                      return (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-4 py-3 font-medium text-gray-900">
                            <div className="flex items-center gap-2">
                              <span>{p.symbol ?? "—"}</span>
                              {p.asset_type === "OPTION" && (
                                <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-700">
                                  Option
                                </span>
                              )}
                            </div>
                            {p.asset_type === "OPTION" && p.description && (
                              <div className="text-xs font-normal text-gray-500">
                                {p.description}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3 capitalize text-gray-600">
                            {p.status}
                            {p.needs_basis && (
                              <span
                                title="Closed a position opened before this week and SnapTrade had no cost basis — realized P/L excludes it."
                                className="ml-1 text-amber-500"
                              >
                                ⚠
                              </span>
                            )}
                            {p.needs_price && (
                              <span
                                title="No current price available to mark this open position."
                                className="ml-1 text-amber-500"
                              >
                                ⚠
                              </span>
                            )}
                          </td>
                          <td
                            className={`px-4 py-3 ${
                              p.realized_pnl >= 0
                                ? "text-emerald-600"
                                : "text-rose-600"
                            }`}
                          >
                            {signed(p.realized_pnl)}
                          </td>
                          <td
                            className={`px-4 py-3 ${
                              p.unrealized_pnl >= 0
                                ? "text-emerald-600"
                                : "text-rose-600"
                            }`}
                          >
                            {signed(p.unrealized_pnl)}
                          </td>
                          <td
                            className={`px-4 py-3 font-semibold ${
                              total >= 0 ? "text-emerald-600" : "text-rose-600"
                            }`}
                          >
                            {signed(total)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <div className="border-b border-gray-200 bg-gray-50 px-6 py-4">
              <p className="text-base font-semibold text-gray-900">Trades</p>
              {data.message && (
                <p className="mt-1 text-xs text-gray-500">{data.message}</p>
              )}
            </div>
            {data.trades.length === 0 ? (
              <p className="px-6 py-8 text-center text-sm text-gray-500">
                No trades in this window.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-white">
                    <tr>
                      {["Date", "Symbol", "Action", "Units", "Price", "Amount"].map((h) => (
                        <th
                          key={h}
                          className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {data.trades.map((t, i) => (
                      <tr key={i} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-gray-700">{fmtDate(t.trade_date)}</td>
                        <td className="px-4 py-3 font-medium text-gray-900">
                          <div className="flex items-center gap-2">
                            <span>{t.symbol ?? "—"}</span>
                            {t.asset_type === "OPTION" ? (
                              <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-700">
                                Option
                              </span>
                            ) : null}
                          </div>
                          {t.asset_type === "OPTION" && t.description ? (
                            <div className="text-xs font-normal text-gray-500">
                              {t.description}
                            </div>
                          ) : null}
                        </td>
                        <td
                          className={`px-4 py-3 font-medium ${
                            t.action === "BUY" ? "text-emerald-600" : "text-rose-600"
                          }`}
                        >
                          {t.action}
                        </td>
                        <td className="px-4 py-3 text-gray-700">{t.units.toFixed(4)}</td>
                        <td className="px-4 py-3 text-gray-700">${t.price.toFixed(2)}</td>
                        <td className="px-4 py-3 font-medium text-gray-900">
                          ${fmt(Math.abs(t.amount))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
