"use client";

import { useEffect, useState } from "react";

import api from "@/services/api";

interface TradeRow {
  trade_date: string;
  symbol: string | null;
  description: string | null;
  action: string;
  units: number;
  price: number;
  amount: number;
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
  available: boolean;
  message: string | null;
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
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "up" | "down";
}) {
  const valueColor =
    tone === "up" ? "text-emerald-600" : tone === "down" ? "text-rose-600" : "text-gray-900";
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${valueColor}`}>{value}</p>
    </div>
  );
}

export default function ReportsPage() {
  const [data, setData] = useState<WeeklyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api
      .get<WeeklyReport>("/api/v1/reports/weekly-trades")
      .then(({ data }) => setData(data))
      .catch(() => setError("Failed to load report."))
      .finally(() => setLoading(false));
  }, []);

  const pnlTone =
    data?.week_pnl == null ? "default" : data.week_pnl >= 0 ? "up" : "down";

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Weekly Report</h1>
        {data && (
          <p className="text-sm text-gray-500">
            {fmtDate(data.week_start)} – {fmtDate(data.week_end)}
          </p>
        )}
      </div>

      {error && <p className="text-sm text-rose-500">{error}</p>}

      {loading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : data ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Week P/L"
              value={data.week_pnl == null ? "—" : `$${fmt(data.week_pnl)}`}
              tone={pnlTone}
            />
            <StatCard
              label="Week P/L %"
              value={fmtPct(data.week_pnl_pct)}
              tone={pnlTone}
            />
            <StatCard label="Total Buys" value={`$${fmt(data.total_buys)}`} />
            <StatCard label="Total Sells" value={`$${fmt(data.total_sells)}`} />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard
              label="Start of week value"
              value={data.week_start_value == null ? "—" : `$${fmt(data.week_start_value)}`}
            />
            <StatCard
              label="End of week value"
              value={data.week_end_value == null ? "—" : `$${fmt(data.week_end_value)}`}
            />
            <StatCard label="Deposits this week" value={`$${fmt(data.week_deposits)}`} />
          </div>

          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <div className="border-b border-gray-200 bg-gray-50 px-6 py-4">
              <p className="text-base font-semibold text-gray-900">Trades this week</p>
              {data.message && (
                <p className="mt-1 text-xs text-gray-500">{data.message}</p>
              )}
            </div>
            {data.trades.length === 0 ? (
              <p className="px-6 py-8 text-center text-sm text-gray-500">
                No trades in the past 7 days.
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
                          {t.symbol ?? "—"}
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
