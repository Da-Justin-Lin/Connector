"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import api from "@/services/api";

type Range = "1D" | "1M" | "3M" | "6M" | "YTD" | "1Y";

const RANGES: { label: Range; query: string }[] = [
  { label: "1D", query: "1d" },
  { label: "1M", query: "1m" },
  { label: "3M", query: "3m" },
  { label: "6M", query: "6m" },
  { label: "YTD", query: "ytd" },
  { label: "1Y", query: "1y" },
];

function formatXTick(value: string, isIntraday: boolean) {
  if (!value) return "";
  if (isIntraday) {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatTooltipLabel(value: string, isIntraday: boolean) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return isIntraday
    ? d.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      })
    : d.toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
      });
}

interface HistoryPoint {
  date: string;
  total_value: number;
}

interface HistoryResponse {
  series: HistoryPoint[];
  available: boolean;
  message: string | null;
}

interface BenchmarkPoint {
  date: string;
  value: number;
}

interface BenchmarkResponse {
  symbol: string;
  range: string;
  series: BenchmarkPoint[];
  available: boolean;
  message: string | null;
}

interface PortfolioReturns {
  current_value: number;
  total_principal: number;
  all_time_return: number;
  all_time_return_pct: number;
  day_change: number | null;
  day_change_pct: number | null;
  ytd_change: number | null;
  ytd_change_pct: number | null;
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

function fmtMoney(n: number | null | undefined) {
  if (n == null) return "—";
  const sign = n >= 0 ? "+" : "-";
  return `${sign}$${fmt(Math.abs(n))}`;
}

function ReturnCard({
  label,
  pct,
  delta,
  tone,
}: {
  label: string;
  pct: number | null;
  delta: number | null;
  tone?: "default" | "up" | "down";
}) {
  const valueColor =
    tone === "up" ? "text-emerald-600" : tone === "down" ? "text-rose-600" : "text-gray-900";
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`mt-1 text-xl font-bold ${valueColor}`}>{fmtPct(pct)}</p>
      <p className="text-xs text-gray-500">{fmtMoney(delta)}</p>
    </div>
  );
}

interface PortfolioTrendProps {
  accountId?: string | null;
}

export default function PortfolioTrend({ accountId = null }: PortfolioTrendProps) {
  const [range, setRange] = useState<Range>("1Y");
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);
  const [returns, setReturns] = useState<PortfolioReturns | null>(null);
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

    api
      .get<BenchmarkResponse>(`/api/v1/reports/benchmark?range=${rangeQuery}&symbol=SPY`)
      .then(({ data }) => setBenchmark(data))
      .catch(() =>
        setBenchmark({
          symbol: "SPY",
          range: rangeQuery,
          series: [],
          available: false,
          message: null,
        }),
      );
  }, [range, accountId]);

  useEffect(() => {
    api
      .get<PortfolioReturns>("/api/v1/reports/portfolio-returns")
      .then(({ data }) => setReturns(data))
      .catch(() => setReturns(null));
  }, [accountId]);

  // Merge history + benchmark into a unified time series.
  // Both are normalized to start at 0% so they're directly comparable.
  const chartData = useMemo(() => {
    const portfolio = history?.series ?? [];
    if (portfolio.length === 0) return [];

    const portfolioBase = portfolio[0].total_value;
    const benchmarkPoints = benchmark?.series ?? [];
    const benchmarkBase = benchmarkPoints[0]?.value;

    // Index benchmark by date (YYYY-MM-DD prefix) for lookups
    const benchmarkByDate = new Map<string, number>();
    for (const p of benchmarkPoints) {
      benchmarkByDate.set(p.date.slice(0, 10), p.value);
    }

    return portfolio.map((p) => {
      const dateKey = p.date.slice(0, 10);
      const benchValue = benchmarkByDate.get(dateKey);
      return {
        date: p.date,
        value: p.total_value,
        valuePct:
          portfolioBase > 0 ? ((p.total_value - portfolioBase) / portfolioBase) * 100 : 0,
        benchmarkPct:
          benchValue !== undefined && benchmarkBase
            ? ((benchValue - benchmarkBase) / benchmarkBase) * 100
            : null,
      };
    });
  }, [history, benchmark]);

  const allTimeTone =
    returns == null
      ? "default"
      : returns.all_time_return >= 0
        ? "up"
        : "down";
  const dayTone =
    returns?.day_change == null
      ? "default"
      : returns.day_change >= 0
        ? "up"
        : "down";
  const ytdTone =
    returns?.ytd_change == null
      ? "default"
      : returns.ytd_change >= 0
        ? "up"
        : "down";

  return (
    <div className="flex flex-col gap-6">
      {returns && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <ReturnCard
            label="1D"
            pct={returns.day_change_pct}
            delta={returns.day_change}
            tone={dayTone}
          />
          <ReturnCard
            label="YTD"
            pct={returns.ytd_change_pct}
            delta={returns.ytd_change}
            tone={ytdTone}
          />
          <ReturnCard
            label="All Time (vs principal)"
            pct={returns.all_time_return_pct}
            delta={returns.all_time_return}
            tone={allTimeTone}
          />
        </div>
      )}

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm text-gray-500">Portfolio Trend vs S&amp;P 500</p>
            {chartData.length > 0 && (
              <p className="mt-1 text-2xl font-bold text-gray-900">
                ${fmt(chartData[chartData.length - 1].value)}
              </p>
            )}
          </div>
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

        <div className="h-64">
          {historyLoading ? (
            <div className="flex h-full items-center justify-center text-sm text-gray-400">
              Loading…
            </div>
          ) : history && !history.available ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-gray-500">
              <p>{history.message ?? "Historical data is not available yet."}</p>
            </div>
          ) : chartData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-center text-sm text-gray-400">
              {history?.message ?? "No data points in this range yet."}
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
                  tickFormatter={(v: string) => formatXTick(v, range === "1D")}
                />
                <YAxis
                  yAxisId="pct"
                  tick={{ fontSize: 11, fill: "#9ca3af" }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`}
                  width={56}
                />
                <Tooltip
                  formatter={(value, name) => {
                    if (value == null || (typeof value === "number" && isNaN(value))) {
                      return ["—", name as string];
                    }
                    const pct = Number(value);
                    const sign = pct >= 0 ? "+" : "";
                    return [`${sign}${pct.toFixed(2)}%`, name as string];
                  }}
                  labelFormatter={(label) =>
                    formatTooltipLabel(String(label ?? ""), range === "1D")
                  }
                  labelStyle={{ color: "#374151", fontSize: 12 }}
                  contentStyle={{
                    borderRadius: 8,
                    border: "1px solid #e5e7eb",
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} iconType="line" />
                <Line
                  yAxisId="pct"
                  type="monotone"
                  dataKey="valuePct"
                  name="Portfolio"
                  stroke="#4f46e5"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="pct"
                  type="monotone"
                  dataKey="benchmarkPct"
                  name="S&P 500"
                  stroke="#9ca3af"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
