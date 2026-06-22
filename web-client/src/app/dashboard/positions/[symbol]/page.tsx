"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import PriceChart from "@/components/PriceChart";
import api from "@/services/api";

interface PositionTrade {
  trade_date: string;
  action: string;
  units: number;
  price: number;
  amount: number;
  asset_type: string;
  description: string | null;
}

interface PositionDetail {
  symbol: string;
  name: string | null;
  held: boolean;
  quantity: number;
  avg_cost: number | null;
  cost_basis: number | null;
  current_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  accounts: number;
  trades: PositionTrade[];
}

function fmt(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(rate: number | null) {
  if (rate == null) return "—";
  const pct = rate * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function fmtDate(iso: string) {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function StatCard({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "up" | "down" }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-content";
  return (
    <div className="card card-hover p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={`num mt-1 text-2xl font-bold tracking-tight ${color}`}>{value}</p>
    </div>
  );
}

export default function PositionPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol).toUpperCase();

  const [detail, setDetail] = useState<PositionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [price, setPrice] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true);
    api
      .get<PositionDetail>(`/api/v1/snaptrade/positions/${encodeURIComponent(symbol)}`)
      .then(({ data }) => setDetail(data))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [symbol]);

  const pnlTone =
    detail?.unrealized_pnl == null ? "default" : detail.unrealized_pnl >= 0 ? "up" : "down";
  const signed = (n: number | null) =>
    n == null ? "—" : `${n >= 0 ? "+" : "−"}$${fmt(Math.abs(n))}`;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link href="/dashboard" className="text-sm text-brand hover:underline">
          ← Back to overview
        </Link>
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-content">{symbol}</h1>
          <p className="text-sm text-muted">{detail?.name ?? "—"}</p>
        </div>
        {price !== null && (
          <p className="num text-3xl font-bold tracking-tight text-content">${fmt(price)}</p>
        )}
      </div>

      {/* Price chart */}
      <div className="card p-4">
        <div className="h-80">
          <PriceChart symbol={symbol} onLatest={(close) => setPrice(close)} />
        </div>
      </div>

      {/* Your position */}
      {loading ? (
        <p className="text-sm text-faint">Loading position…</p>
      ) : detail && detail.held ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Quantity" value={detail.quantity.toLocaleString("en-US", { maximumFractionDigits: 4 })} />
          <StatCard label="Avg cost" value={detail.avg_cost == null ? "—" : `$${fmt(detail.avg_cost)}`} />
          <StatCard label="Market value" value={detail.market_value == null ? "—" : `$${fmt(detail.market_value)}`} />
          <StatCard
            label="Unrealized P/L"
            value={detail.unrealized_pnl == null ? "—" : `${signed(detail.unrealized_pnl)} (${fmtPct(detail.unrealized_pnl_pct)})`}
            tone={pnlTone}
          />
        </div>
      ) : detail ? (
        <p className="text-sm text-muted">
          You don&apos;t currently hold {symbol}.
          {detail.trades.length > 0 ? " Past trades are shown below." : ""}
        </p>
      ) : (
        <p className="text-sm text-down">Failed to load position details.</p>
      )}

      {/* Trade history */}
      <div className="overflow-hidden card">
        <div className="border-b border-line bg-surface-2 px-6 py-4">
          <p className="text-base font-semibold text-content">Your trade history</p>
          <p className="mt-0.5 text-xs text-muted">Filled buys and sells for {symbol} across your accounts.</p>
        </div>
        {!detail || detail.trades.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-muted">
            {loading ? "Loading…" : "No recorded trades for this symbol."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm">
              <thead className="bg-surface">
                <tr>
                  {["Date", "Action", "Units", "Price", "Amount"].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {detail.trades.map((t, i) => (
                  <tr key={i} className="hover:bg-surface-2">
                    <td className="px-4 py-3 text-content">{fmtDate(t.trade_date)}</td>
                    <td className={`px-4 py-3 font-medium ${t.action === "BUY" ? "text-up" : "text-down"}`}>
                      {t.action}
                      {t.asset_type === "OPTION" && (
                        <span className="ml-2 rounded bg-brand-soft px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand">
                          Option
                        </span>
                      )}
                      {t.asset_type === "OPTION" && t.description && (
                        <div className="text-xs font-normal text-muted">{t.description}</div>
                      )}
                    </td>
                    <td className="num px-4 py-3 text-content">{t.units.toFixed(4)}</td>
                    <td className="num px-4 py-3 text-content">${t.price.toFixed(2)}</td>
                    <td className="num px-4 py-3 font-medium text-content">${fmt(Math.abs(t.amount))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
