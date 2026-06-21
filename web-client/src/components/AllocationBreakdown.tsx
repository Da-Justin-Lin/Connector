"use client";

import { useEffect, useMemo, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import api from "@/services/api";
import { useCachedResource } from "@/hooks/useCachedResource";

interface Holding {
  ticker: string | null;
  name: string | null;
  security_type: string | null;
  quantity: number;
  institution_price: number;
  market_value: number;
  cost_basis: number | null;
}

interface AccountSection {
  cash: number;
  holdings: Holding[];
}

interface HoldingsData {
  accounts: AccountSection[];
  total_value: number;
  total_cash: number;
  stale?: boolean;
}

interface SectorsResponse {
  sectors: Record<string, string | null>;
}

type Mode = "asset" | "sector" | "holdings";

const MODES: { key: Mode; label: string }[] = [
  { key: "asset", label: "Asset class" },
  { key: "sector", label: "Sector" },
  { key: "holdings", label: "Holdings" },
];

// A fixed, readable palette; slices beyond it cycle back around.
const PALETTE = [
  "#6366f1", "#10b981", "#f59e0b", "#ef4444", "#3b82f6", "#8b5cf6",
  "#ec4899", "#14b8a6", "#f97316", "#84cc16", "#06b6d4", "#a855f7",
];
const CASH_COLOR = "#9ca3af";
const OTHER_COLOR = "#cbd5e1";

// SnapTrade `kind` codes / strings → friendly asset-class labels.
const ASSET_LABELS: Record<string, string> = {
  cs: "Stocks",
  equity: "Stocks",
  stock: "Stocks",
  et: "ETFs",
  etf: "ETFs",
  crypto: "Crypto",
  cryptocurrency: "Crypto",
  option: "Options",
  opt: "Options",
  mf: "Funds",
  mutualfund: "Funds",
  bnd: "Bonds",
  bond: "Bonds",
};

function assetLabel(securityType: string | null): string {
  if (!securityType) return "Other";
  const key = securityType.toLowerCase();
  return ASSET_LABELS[key] ?? securityType.charAt(0).toUpperCase() + securityType.slice(1);
}

function fmt(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface Slice {
  label: string;
  value: number;
  color: string;
}

export default function AllocationBreakdown({ accountId = null }: { accountId?: string | null }) {
  const qs = accountId ? `?account_id=${accountId}` : "";
  const { data, loading, error } = useCachedResource<HoldingsData>(
    "holdings",
    accountId ?? "ALL",
    `/api/v1/snaptrade/holdings${qs}`,
    { isStale: (d) => !!d.stale },
  );

  const [mode, setMode] = useState<Mode>("asset");
  const [sectors, setSectors] = useState<Record<string, string | null>>({});
  const [sectorLoading, setSectorLoading] = useState(false);

  // Flatten every account's holdings into one list (plus aggregate cash).
  const { holdings, cash } = useMemo(() => {
    const all: Holding[] = [];
    let totalCash = 0;
    for (const acct of data?.accounts ?? []) {
      totalCash += acct.cash;
      for (const h of acct.holdings) all.push(h);
    }
    return { holdings: all, cash: totalCash };
  }, [data]);

  const tickers = useMemo(
    () => Array.from(new Set(holdings.map((h) => h.ticker).filter((t): t is string => !!t))),
    [holdings],
  );

  // Lazily fetch sector classifications the first time Sector mode is shown.
  useEffect(() => {
    if (mode !== "sector" || tickers.length === 0) return;
    const missing = tickers.filter((t) => !(t in sectors));
    if (missing.length === 0) return;
    setSectorLoading(true);
    api
      .get<SectorsResponse>(`/api/v1/market/sectors?symbols=${encodeURIComponent(tickers.join(","))}`)
      .then(({ data }) => setSectors((prev) => ({ ...prev, ...data.sectors })))
      .catch(() => {})
      .finally(() => setSectorLoading(false));
  }, [mode, tickers, sectors]);

  const slices = useMemo<Slice[]>(() => {
    if (holdings.length === 0 && cash === 0) return [];

    // Holdings mode: one slice per position, smallest collapsed into "Other".
    if (mode === "holdings") {
      const sorted = [...holdings].sort((a, b) => b.market_value - a.market_value);
      const top = sorted.slice(0, 10);
      const rest = sorted.slice(10);
      const out: Slice[] = top.map((h, i) => ({
        label: h.ticker ?? h.name ?? "—",
        value: h.market_value,
        color: PALETTE[i % PALETTE.length],
      }));
      const restSum = rest.reduce((s, h) => s + h.market_value, 0);
      if (restSum > 0) out.push({ label: `Other (${rest.length})`, value: restSum, color: OTHER_COLOR });
      if (cash > 0) out.push({ label: "Cash", value: cash, color: CASH_COLOR });
      return out;
    }

    // Asset-class and sector modes both bucket market value into groups.
    const groups = new Map<string, number>();
    for (const h of holdings) {
      const key =
        mode === "asset"
          ? assetLabel(h.security_type)
          : (h.ticker && sectors[h.ticker]) || "Unclassified";
      groups.set(key, (groups.get(key) ?? 0) + h.market_value);
    }
    const entries = Array.from(groups.entries()).sort((a, b) => b[1] - a[1]);
    const out: Slice[] = entries.map(([label, value], i) => ({
      label,
      value,
      color: label === "Unclassified" ? OTHER_COLOR : PALETTE[i % PALETTE.length],
    }));
    if (cash > 0) out.push({ label: "Cash", value: cash, color: CASH_COLOR });
    return out;
  }, [mode, holdings, cash, sectors]);

  const total = useMemo(() => slices.reduce((s, x) => s + x.value, 0), [slices]);

  // Concentration callout: flag any single position above 25% of the book.
  const concentration = useMemo(() => {
    if (total <= 0 || holdings.length === 0) return null;
    const top = holdings.reduce((m, h) => (h.market_value > m.market_value ? h : m), holdings[0]);
    const pct = top.market_value / total;
    if (pct < 0.25 || !top.ticker) return null;
    return { ticker: top.ticker, pct };
  }, [holdings, total]);

  if (error) return null;

  return (
    <div className="card p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-base font-semibold text-content">Allocation</p>
        <div className="flex gap-1 rounded-lg bg-surface-2 p-1">
          {MODES.map((m) => (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                mode === m.key
                  ? "bg-surface text-content shadow-sm"
                  : "text-muted hover:text-content"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="mt-6 text-sm text-faint">Loading allocation…</p>
      ) : slices.length === 0 ? (
        <p className="mt-6 text-sm text-muted">No holdings to break down yet.</p>
      ) : (
        <div className="mt-4 flex flex-col gap-6 sm:flex-row sm:items-center">
          <div className="relative h-56 w-full sm:w-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={slices}
                  dataKey="value"
                  nameKey="label"
                  innerRadius={64}
                  outerRadius={92}
                  paddingAngle={1}
                  stroke="none"
                >
                  {slices.map((s, i) => (
                    <Cell key={i} fill={s.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value, label) => {
                    const v = Number(value);
                    return [`$${fmt(v)} (${((v / total) * 100).toFixed(1)}%)`, String(label)];
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-xs text-muted">Total</span>
              <span className="text-lg font-bold text-content">${fmt(total)}</span>
            </div>
          </div>

          <div className="flex-1">
            {mode === "sector" && sectorLoading && (
              <p className="mb-2 text-xs text-brand">Classifying sectors…</p>
            )}
            <ul className="space-y-1.5">
              {slices.map((s, i) => (
                <li key={i} className="flex items-center justify-between gap-3 text-sm">
                  <span className="flex items-center gap-2 truncate">
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: s.color }} />
                    <span className="truncate text-content">{s.label}</span>
                  </span>
                  <span className="shrink-0 text-muted">
                    {((s.value / total) * 100).toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
            {concentration && (
              <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">
                ⚠ {concentration.ticker} is {(concentration.pct * 100).toFixed(0)}% of your
                portfolio — heavily concentrated.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
