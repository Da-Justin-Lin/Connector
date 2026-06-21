"use client";

import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import AnimatedNumber from "@/components/AnimatedNumber";
import { useCachedResource } from "@/hooks/useCachedResource";
import { useThemeColors } from "@/hooks/useThemeColors";

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
  stale?: boolean;
  last_synced_at?: string | null;
}

interface Deposit {
  id: string;
  investment_account_id: string;
  amount: number;
  deposited_at: string;
}

interface DepositsResponse {
  deposits: Deposit[];
  total_principal: number;
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
    tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-content";
  return (
    <div className="card card-hover p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={`num mt-1 text-xl font-bold ${valueColor}`}>{fmtPct(pct)}</p>
      <p className="num text-xs text-muted">{fmtMoney(delta)}</p>
    </div>
  );
}

interface ChartPoint {
  date: string;
  value: number;
  principal: number;
  delta: number;
  portfolioPct: number | null;
  benchmarkPct: number | null;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ payload?: ChartPoint }>;
  label?: string | number;
  isIntraday: boolean;
}

function CustomTooltip({ active, payload, label, isIntraday }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload;
  if (!point) return null;

  const portfolioColor =
    point.portfolioPct == null
      ? "text-muted"
      : point.portfolioPct >= 0
        ? "text-up"
        : "text-down";

  const benchmarkColor =
    point.benchmarkPct == null
      ? "text-muted"
      : point.benchmarkPct >= 0
        ? "text-up"
        : "text-down";

  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-content">
        {formatTooltipLabel(String(label ?? ""), isIntraday)}
      </p>
      <div className="mt-1 space-y-0.5">
        <p>
          <span className="inline-block h-2 w-2 rounded-full bg-brand mr-1.5 align-middle" />
          <span className="text-muted">Portfolio: </span>
          <span className="font-semibold text-content">${fmt(point.value)}</span>
          <span className={`ml-2 font-semibold ${portfolioColor}`}>
            {point.portfolioPct == null
              ? ""
              : `${point.portfolioPct >= 0 ? "+" : ""}${point.portfolioPct.toFixed(2)}%`}
          </span>
        </p>
        {point.principal > 0 && (
          <p className="text-muted">
            Principal: ${fmt(point.principal)} · Δ {fmtMoney(point.delta)}
          </p>
        )}
        {point.benchmarkPct != null && (
          <p>
            <span className="inline-block h-2 w-2 rounded-full bg-faint mr-1.5 align-middle" />
            <span className="text-muted">S&amp;P 500: </span>
            <span className={`font-semibold ${benchmarkColor}`}>
              {point.benchmarkPct >= 0 ? "+" : ""}
              {point.benchmarkPct.toFixed(2)}%
            </span>
          </p>
        )}
      </div>
    </div>
  );
}

interface PortfolioTrendProps {
  accountId?: string | null;
}

export default function PortfolioTrend({ accountId = null }: PortfolioTrendProps) {
  const [range, setRange] = useState<Range>("1Y");
  const c = useThemeColors();
  const rangeQuery = RANGES.find((r) => r.label === range)?.query || "1y";
  const acct = accountId ?? "ALL";
  const acctQs = accountId ? `&account_id=${accountId}` : "";
  const acctQsOnly = accountId ? `?account_id=${accountId}` : "";

  const historyRes = useCachedResource<HistoryResponse>(
    "history",
    `${acct}|${rangeQuery}`,
    `/api/v1/snaptrade/history?range=${rangeQuery}${acctQs}`,
  );
  const benchmarkRes = useCachedResource<BenchmarkResponse>(
    "benchmark",
    rangeQuery,
    `/api/v1/reports/benchmark?range=${rangeQuery}&symbol=SPY`,
  );
  const returnsRes = useCachedResource<PortfolioReturns>(
    "returns",
    acct,
    `/api/v1/reports/portfolio-returns${acctQsOnly}`,
    { isStale: (d) => !!d.stale },
  );
  const depositsRes = useCachedResource<DepositsResponse>(
    "deposits",
    acct,
    `/api/v1/deposits${acctQsOnly}`,
  );

  const history = historyRes.data;
  const benchmark = benchmarkRes.data;
  const returns = returnsRes.data;
  const deposits = useMemo(() => depositsRes.data?.deposits ?? [], [depositsRes.data]);
  const historyLoading = historyRes.loading;
  const updating =
    (returnsRes.revalidating || returns?.stale || historyRes.revalidating) &&
    (history != null || returns != null);

  const chartData = useMemo<ChartPoint[]>(() => {
    const portfolio = history?.series ?? [];
    if (portfolio.length === 0) return [];

    // Sort deposits ascending so we can use a running sum
    const sortedDeposits = [...deposits].sort((a, b) =>
      a.deposited_at.localeCompare(b.deposited_at),
    );

    // If a specific account is selected, only that account's deposits matter.
    // (The deposits endpoint already filtered when accountId was passed.)
    const benchmarkPoints = benchmark?.series ?? [];
    const benchmarkBase = benchmarkPoints[0]?.value;
    const benchmarkByDate = new Map<string, number>();
    for (const p of benchmarkPoints) benchmarkByDate.set(p.date.slice(0, 10), p.value);

    return portfolio.map((p) => {
      const dateKey = p.date.slice(0, 10);
      const principalAtPoint = sortedDeposits
        .filter((d) => d.deposited_at <= p.date)
        .reduce((sum, d) => sum + Number(d.amount), 0);

      const delta = p.total_value - principalAtPoint;
      const portfolioPct =
        principalAtPoint > 0 ? (delta / principalAtPoint) * 100 : null;

      const benchValue = benchmarkByDate.get(dateKey);
      const benchmarkPct =
        benchValue !== undefined && benchmarkBase
          ? ((benchValue - benchmarkBase) / benchmarkBase) * 100
          : null;

      return {
        date: p.date,
        value: p.total_value,
        principal: Math.round(principalAtPoint * 100) / 100,
        delta: Math.round(delta * 100) / 100,
        portfolioPct,
        benchmarkPct,
      };
    });
  }, [history, benchmark, deposits]);

  const hasPrincipal = chartData.some((p) => p.principal > 0);
  const showsPortfolioLine = hasPrincipal;

  // When there's no principal data, fall back to "0% baseline = first point of range"
  const fallbackChartData = useMemo<ChartPoint[]>(() => {
    const portfolio = history?.series ?? [];
    if (portfolio.length === 0) return [];
    const base = portfolio[0].total_value;
    const benchmarkPoints = benchmark?.series ?? [];
    const benchmarkBase = benchmarkPoints[0]?.value;
    const benchmarkByDate = new Map<string, number>();
    for (const p of benchmarkPoints) benchmarkByDate.set(p.date.slice(0, 10), p.value);
    return portfolio.map((p) => {
      const dateKey = p.date.slice(0, 10);
      const benchValue = benchmarkByDate.get(dateKey);
      return {
        date: p.date,
        value: p.total_value,
        principal: 0,
        delta: p.total_value - base,
        portfolioPct: base > 0 ? ((p.total_value - base) / base) * 100 : null,
        benchmarkPct:
          benchValue !== undefined && benchmarkBase
            ? ((benchValue - benchmarkBase) / benchmarkBase) * 100
            : null,
      };
    });
  }, [history, benchmark]);

  const displayedData = showsPortfolioLine ? chartData : fallbackChartData;

  const allTimeTone =
    returns == null ? "default" : returns.all_time_return >= 0 ? "up" : "down";
  const dayTone =
    returns?.day_change == null ? "default" : returns.day_change >= 0 ? "up" : "down";
  const ytdTone =
    returns?.ytd_change == null ? "default" : returns.ytd_change >= 0 ? "up" : "down";

  const currentValueNum =
    displayedData.length > 0
      ? displayedData[displayedData.length - 1].value
      : returns
        ? returns.current_value
        : null;

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

      <div className="card p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="flex items-center gap-2 text-sm text-muted">
              <span>Portfolio Trend vs S&amp;P 500</span>
              {updating && (
                <span className="inline-flex items-center gap-1.5 text-xs text-brand">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
                  Updating…
                </span>
              )}
            </p>
            <p className="text-sm text-muted">
              {showsPortfolioLine ? (
                <span className="text-xs text-faint">(baseline = your principal)</span>
              ) : (
                <span className="text-xs text-faint">
                  (add deposits to baseline against principal)
                </span>
              )}
            </p>
            {currentValueNum != null ? (
              <AnimatedNumber
                value={currentValueNum}
                prefix="$"
                sensitive
                className="mt-1 block text-3xl font-bold tracking-tight text-content"
              />
            ) : (
              <p className="num mt-1 text-3xl font-bold tracking-tight text-content">—</p>
            )}
          </div>
          <div className="flex gap-1 rounded-lg bg-surface-2 p-1">
            {RANGES.map((r) => (
              <button
                key={r.label}
                onClick={() => setRange(r.label)}
                className={`tap rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  range === r.label
                    ? "bg-surface text-content shadow-sm"
                    : "text-muted hover:text-content"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div className="h-64">
          {historyLoading ? (
            <div className="flex h-full items-center justify-center text-sm text-faint">
              Loading…
            </div>
          ) : history && !history.available ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted">
              <p>{history.message ?? "Historical data is not available yet."}</p>
            </div>
          ) : displayedData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-center text-sm text-faint">
              {history?.message ?? "No data points in this range yet."}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={displayedData}
                margin={{ top: 8, right: 8, left: 8, bottom: 8 }}
                className="chart-glow"
              >
                <defs>
                  <linearGradient id="portfolioFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={c.brand} stopOpacity={0.32} />
                    <stop offset="100%" stopColor={c.brand} stopOpacity={0} />
                  </linearGradient>
                </defs>
                {/* Just a few faint dotted horizontals — no vertical clutter. */}
                <CartesianGrid vertical={false} strokeDasharray="2 6" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: c.faint }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={32}
                  tickFormatter={(v: string) => formatXTick(v, range === "1D")}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: c.faint }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`}
                  width={56}
                />
                <Tooltip content={<CustomTooltip isIntraday={range === "1D"} />} />
                <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" />
                <Area
                  type="monotone"
                  dataKey="portfolioPct"
                  name="Portfolio"
                  stroke={c.brand}
                  strokeWidth={2.5}
                  fill="url(#portfolioFill)"
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 0, fill: c.brand }}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="benchmarkPct"
                  name="S&P 500"
                  stroke={c.faint}
                  strokeWidth={1.75}
                  strokeDasharray="4 4"
                  dot={false}
                  connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
