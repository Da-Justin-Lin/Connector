"use client";

import { useEffect, useState } from "react";

import FearGreedGauge, { type FearGreed } from "@/components/FearGreedGauge";
import MarketSnapshotCard, { type Snapshot } from "@/components/MarketSnapshotCard";
import QuoteGrid from "@/components/QuoteGrid";
import api from "@/services/api";

// Symbols shown on the macro tab (must be on the backend allow-list).
const SYMBOLS = ["SPY", "QQQ", "DIA", "IWM", "BTC-USD", "ETH-USD", "GLD", "^VIX"];
const SNAPSHOT_POLL = 60_000;

// Treasury yields. 10Y − 3M spread is the recession-watch gauge (inversion < 0).
const YIELD_SYMBOLS = ["^IRX", "^FVX", "^TNX", "^TYX"];
const YIELD_LABELS: Record<string, string> = {
  "^IRX": "3-Month",
  "^FVX": "5-Year",
  "^TNX": "10-Year",
  "^TYX": "30-Year",
};

const SECTOR_SYMBOLS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"];
const SECTOR_LABELS: Record<string, string> = {
  XLK: "Technology",
  XLF: "Financials",
  XLE: "Energy",
  XLV: "Health Care",
  XLY: "Cons. Disc.",
  XLP: "Cons. Staples",
  XLI: "Industrials",
  XLB: "Materials",
  XLU: "Utilities",
  XLRE: "Real Estate",
  XLC: "Comm. Svcs.",
};

const COMMODITY_SYMBOLS = ["CL=F", "NG=F", "GC=F", "SI=F", "HG=F", "DX=F"];
const COMMODITY_LABELS: Record<string, string> = {
  "CL=F": "Crude Oil",
  "NG=F": "Nat Gas",
  "GC=F": "Gold",
  "SI=F": "Silver",
  "HG=F": "Copper",
  "DX=F": "US Dollar",
};

interface SnapshotsResponse {
  snapshots: Snapshot[];
  available: boolean;
  message: string | null;
}

interface EarningsEvent {
  symbol: string;
  date: string;
}

interface EarningsResponse {
  events: EarningsEvent[];
  available: boolean;
  message: string | null;
}

function fmtEarningsDate(iso: string) {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export default function MacroPage() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [snapLoading, setSnapLoading] = useState(true);
  const [snapError, setSnapError] = useState<string | null>(null);

  const [fg, setFg] = useState<FearGreed | null>(null);
  const [cryptoFg, setCryptoFg] = useState<FearGreed | null>(null);
  const [earnings, setEarnings] = useState<EarningsEvent[] | null>(null);
  const [earningsMsg, setEarningsMsg] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Market snapshots — initial load + background polling.
  useEffect(() => {
    let cancelled = false;
    const load = (initial: boolean) => {
      if (initial) setSnapLoading(true);
      api
        .get<SnapshotsResponse>(`/api/v1/market/snapshots?symbols=${SYMBOLS.join(",")}`)
        .then(({ data }) => {
          if (cancelled) return;
          if (!data.available) setSnapError(data.message ?? "Market data unavailable.");
          else setSnapError(null);
          setSnapshots(data.snapshots);
          setLastUpdated(new Date());
        })
        .catch(() => {
          if (!cancelled && initial) setSnapError("Failed to load market data.");
        })
        .finally(() => {
          if (!cancelled && initial) setSnapLoading(false);
        });
    };
    load(true);
    const id = setInterval(() => load(false), SNAPSHOT_POLL);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Fear & Greed.
  useEffect(() => {
    let cancelled = false;
    api
      .get<FearGreed>("/api/v1/market/fear-greed")
      .then(({ data }) => {
        if (!cancelled) setFg(data);
      })
      .catch(() => {
        if (!cancelled)
          setFg({
            score: null,
            rating: null,
            updated_at: null,
            prev_close: null,
            prev_week: null,
            prev_month: null,
            prev_year: null,
            available: false,
            message: "Unavailable right now.",
          });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Crypto Fear & Greed (alternative.me).
  useEffect(() => {
    let cancelled = false;
    api
      .get<FearGreed>("/api/v1/market/crypto-fear-greed")
      .then(({ data }) => {
        if (!cancelled) setCryptoFg(data);
      })
      .catch(() => {
        if (!cancelled)
          setCryptoFg({
            score: null,
            rating: null,
            prev_close: null,
            available: false,
            message: "Unavailable right now.",
          });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Upcoming earnings.
  useEffect(() => {
    let cancelled = false;
    api
      .get<EarningsResponse>("/api/v1/market/earnings?days=14")
      .then(({ data }) => {
        if (cancelled) return;
        setEarnings(data.events);
        if (!data.available) setEarningsMsg(data.message ?? "Unavailable.");
      })
      .catch(() => {
        if (!cancelled) {
          setEarnings([]);
          setEarningsMsg("Failed to load earnings.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Macro</h1>
          <p className="text-sm text-gray-500">A quick read on how the market is moving today.</p>
        </div>
        {lastUpdated && (
          <p className="text-xs text-gray-400">
            Updated{" "}
            {lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </p>
        )}
      </div>

      {snapError && <p className="text-sm text-rose-500">{snapError}</p>}

      {/* Day charts */}
      {snapLoading ? (
        <p className="text-sm text-gray-400">Loading market data…</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {snapshots.map((s) => (
            <MarketSnapshotCard key={s.symbol} snap={s} />
          ))}
        </div>
      )}

      {/* Treasury yields + the 10Y−3M spread */}
      <QuoteGrid
        title="Treasury yields"
        subtitle="US government bond yields"
        symbols={YIELD_SYMBOLS}
        labels={YIELD_LABELS}
        kind="yield"
        renderFooter={(quotes) => {
          const tenY = quotes.find((q) => q.symbol === "^TNX")?.last ?? null;
          const threeM = quotes.find((q) => q.symbol === "^IRX")?.last ?? null;
          if (tenY == null || threeM == null) return null;
          const spread = tenY - threeM;
          const inverted = spread < 0;
          return (
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">10Y − 3M spread</span>
              <span className={`font-semibold ${inverted ? "text-rose-600" : "text-emerald-600"}`}>
                {spread >= 0 ? "+" : "−"}
                {Math.abs(spread).toFixed(2)} pts
                {inverted && <span className="ml-2 font-normal text-rose-500">(inverted)</span>}
              </span>
            </div>
          );
        }}
      />

      {/* Sector performance heatmap */}
      <QuoteGrid
        title="Sector performance"
        subtitle="S&P 500 sectors, today"
        symbols={SECTOR_SYMBOLS}
        labels={SECTOR_LABELS}
        kind="price"
        heatmap
        sortByChange
      />

      {/* Commodities + the dollar */}
      <QuoteGrid
        title="Commodities & the dollar"
        symbols={COMMODITY_SYMBOLS}
        labels={COMMODITY_LABELS}
        kind="price"
      />

      {/* Sentiment */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {fg ? (
          <FearGreedGauge fg={fg} title="Fear & Greed" source="CNN · Stocks" />
        ) : (
          <div className="rounded-xl border border-gray-200 bg-white p-5 text-sm text-gray-400 shadow-sm">
            Loading sentiment…
          </div>
        )}
        {cryptoFg ? (
          <FearGreedGauge fg={cryptoFg} title="Crypto Fear & Greed" source="alternative.me" />
        ) : (
          <div className="rounded-xl border border-gray-200 bg-white p-5 text-sm text-gray-400 shadow-sm">
            Loading crypto sentiment…
          </div>
        )}
      </div>

      {/* Earnings */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-5 py-4">
          <div>
            <p className="text-base font-semibold text-gray-900">Earnings this week</p>
            <p className="mt-0.5 text-xs text-gray-500">Upcoming reports from mega-cap names (next 14 days)</p>
          </div>
        </div>
        {earnings == null ? (
          <p className="px-5 py-8 text-center text-sm text-gray-400">Loading…</p>
        ) : earnings.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-gray-500">
            {earningsMsg ?? "No upcoming earnings from the watchlist."}
          </p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {earnings.map((e) => (
              <li key={e.symbol} className="flex items-center justify-between px-5 py-3">
                <span className="text-sm font-medium text-gray-900">{e.symbol}</span>
                <span className="text-sm text-gray-600">{fmtEarningsDate(e.date)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
