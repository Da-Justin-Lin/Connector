"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import api from "@/services/api";

type Range = "1M" | "3M" | "6M" | "YTD" | "1Y";

const RANGES: { label: Range; query: string }[] = [
  { label: "1M", query: "1m" },
  { label: "3M", query: "3m" },
  { label: "6M", query: "6m" },
  { label: "YTD", query: "ytd" },
  { label: "1Y", query: "1y" },
];

interface HistoryPoint {
  date: string;
  total_value: number;
}

interface HistoryResponse {
  series: HistoryPoint[];
  available: boolean;
  message: string | null;
}

interface ReturnsResponse {
  rates: Record<string, number>;
  available: boolean;
  message: string | null;
}

function fmt(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(rate: number | undefined) {
  if (rate === undefined || rate === null) return "—";
  const pct = rate * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function ReturnPill({ label, rate }: { label: string; rate: number | undefined }) {
  const color =
    rate === undefined
      ? "text-gray-400"
      : rate >= 0
        ? "text-emerald-600"
        : "text-rose-600";
  return (
    <div className="flex flex-col items-end">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`text-sm font-semibold ${color}`}>{fmtPct(rate)}</span>
    </div>
  );
}

interface PortfolioTrendProps {
  accountId?: string | null;
}

export default function PortfolioTrend({ accountId = null }: PortfolioTrendProps) {
  const [range, setRange] = useState<Range>("1Y");
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [returns, setReturns] = useState<ReturnsResponse | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);

  useEffect(() => {
    setHistoryLoading(true);
    const rangeQuery = RANGES.find((r) => r.label === range)?.query || "1y";
    const params = new URLSearchParams({ range: rangeQuery });
    if (accountId) params.set("account_id", accountId);
    api
      .get<HistoryResponse>(`/api/v1/snaptrade/history?${params.toString()}`)
      .then(({ data }) => setHistory(data))
      .catch(() =>
        setHistory({ series: [], available: false, message: "Failed to load history." }),
      )
      .finally(() => setHistoryLoading(false));
  }, [range, accountId]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (accountId) params.set("account_id", accountId);
    const qs = params.toString();
    api
      .get<ReturnsResponse>(`/api/v1/snaptrade/returns${qs ? `?${qs}` : ""}`)
      .then(({ data }) => setReturns(data))
      .catch(() =>
        setReturns({ rates: {}, available: false, message: "Failed to load returns." }),
      );
  }, [accountId]);

  const chartData = useMemo(
    () => history?.series.map((p) => ({ date: p.date, value: p.total_value })) ?? [],
    [history],
  );

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm text-gray-500">Portfolio Trend</p>
          {chartData.length > 0 && (
            <p className="mt-1 text-2xl font-bold text-gray-900">
              ${fmt(chartData[chartData.length - 1].value)}
            </p>
          )}
        </div>
        <div className="flex items-center gap-6">
          {returns?.available && (
            <div className="flex gap-4">
              <ReturnPill label="1D" rate={returns.rates["1D"]} />
              <ReturnPill label="1M" rate={returns.rates["1M"]} />
              <ReturnPill label="YTD" rate={returns.rates["YTD"]} />
              <ReturnPill label="1Y" rate={returns.rates["1Y"]} />
            </div>
          )}
          <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
            {RANGES.map((r) => (
              <button
                key={r.label}
                onClick={() => setRange(r.label)}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  range === r.label
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="h-64">
        {historyLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-gray-400">
            Loading…
          </div>
        ) : history && !history.available ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-gray-500">
            <p>{history.message ?? "Historical data is not available yet."}</p>
            <p className="text-xs text-gray-400">
              Upgrade your SnapTrade plan and enable balance history to see your trend.
            </p>
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-gray-400">
            No data points in this range yet.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                tickLine={false}
                axisLine={false}
                minTickGap={32}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
                width={48}
              />
              <Tooltip
                formatter={(value) => [`$${fmt(Number(value))}`, "Total"]}
                labelStyle={{ color: "#374151", fontSize: 12 }}
                contentStyle={{
                  borderRadius: 8,
                  border: "1px solid #e5e7eb",
                  fontSize: 12,
                }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#4f46e5"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
