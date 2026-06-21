"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ResponsiveContainer, Tooltip, Treemap } from "recharts";

import api from "@/services/api";

interface MarketMapItem {
  symbol: string;
  name: string;
  market_cap: number;
  last: number | null;
  change_pct: number | null;
}

interface MarketMapGroup {
  sector: string;
  items: MarketMapItem[];
}

interface MarketMapResponse {
  groups: MarketMapGroup[];
  available: boolean;
  message: string | null;
}

const POLL_MS = 120_000;

// Diverging color: muted slate at 0%, easing toward green (up) / red (down),
// capped at ±3%. A gamma curve keeps small moves from washing out to a flat blob.
function carpetColor(pct: number | null | undefined) {
  if (pct == null) return "#334155"; // slate-700
  const cap = 0.03;
  const t = Math.max(-1, Math.min(1, pct / cap));
  const neutral = [51, 65, 85]; // slate-700
  const green = [34, 197, 94]; // emerald-500
  const red = [244, 63, 94]; // rose-500
  const target = t >= 0 ? green : red;
  const k = Math.pow(Math.abs(t), 0.7);
  const c = neutral.map((n, i) => Math.round(n + (target[i] - n) * k));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function fmtCap(n: number) {
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  return `$${(n / 1e6).toFixed(0)}M`;
}

function fmtPct(pct: number | null | undefined) {
  if (pct == null) return "—";
  const v = pct * 100;
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

interface CellProps {
  depth?: number;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  symbol?: string;
  change_pct?: number | null;
  onSelect?: (symbol: string) => void;
}

// Custom treemap cell: leaves (depth 2) are colored by day change; sector
// rects (depth 1) just get a subtle border to delineate the groups.
function Cell(props: CellProps) {
  const { depth = 0, x = 0, y = 0, width = 0, height = 0, symbol, change_pct, onSelect } = props;

  if (depth === 1) {
    return <rect x={x} y={y} width={width} height={height} fill="none" stroke="#0b0f17" strokeWidth={3} rx={3} />;
  }
  if (depth !== 2 || width <= 0 || height <= 0) return null;

  const showLabel = width > 34 && height > 20;
  // Size the ticker off the smaller dimension so it never overflows the cell.
  const fontSize = Math.max(9, Math.min(15, Math.round(Math.min(width / 4.5, height / 2.6))));
  const showPct = height > 38 && width > 40;

  return (
    <g
      style={{ cursor: symbol ? "pointer" : "default" }}
      onClick={() => symbol && onSelect?.(symbol)}
    >
      <rect
        x={x + 0.5}
        y={y + 0.5}
        width={Math.max(0, width - 1)}
        height={Math.max(0, height - 1)}
        fill={carpetColor(change_pct)}
        stroke="rgba(11,15,23,0.85)"
        strokeWidth={1}
        rx={2}
      />
      {showLabel && (
        <>
          <text
            x={x + width / 2}
            y={y + height / 2 + (showPct ? -2 : fontSize / 3)}
            textAnchor="middle"
            fill="#ffffff"
            stroke="none"
            fontSize={fontSize}
            fontWeight={700}
            letterSpacing={0.3}
            style={{ pointerEvents: "none" }}
          >
            {symbol}
          </text>
          {showPct && (
            <text
              x={x + width / 2}
              y={y + height / 2 + fontSize}
              textAnchor="middle"
              fill="rgba(255,255,255,0.92)"
              stroke="none"
              fontSize={Math.max(8, fontSize - 3)}
              fontWeight={500}
              style={{ pointerEvents: "none" }}
            >
              {fmtPct(change_pct)}
            </text>
          )}
        </>
      )}
    </g>
  );
}

function CarpetTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload?: Record<string, unknown> }> }) {
  if (!active || !payload || payload.length === 0) return null;
  const node = payload[0]?.payload as
    | { symbol?: string; fullName?: string; sector?: string; change_pct?: number | null; size?: number }
    | undefined;
  if (!node?.symbol) return null;
  return (
    <div className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs text-content shadow-lift">
      <p className="font-semibold">
        {node.symbol} <span className="font-normal text-faint">{node.fullName}</span>
      </p>
      <p className="text-faint">{node.sector}</p>
      <p className="mt-1">
        <span className={node.change_pct != null && node.change_pct >= 0 ? "text-up" : "text-down"}>
          {fmtPct(node.change_pct)}
        </span>
        <span className="ml-2 text-faint">{node.size != null ? fmtCap(node.size) : ""}</span>
      </p>
    </div>
  );
}

export default function MarketMap() {
  const router = useRouter();
  const [groups, setGroups] = useState<MarketMapGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = (initial: boolean) => {
      api
        .get<MarketMapResponse>("/api/v1/market/market-map")
        .then(({ data }) => {
          if (cancelled) return;
          setGroups(data.groups);
          setError(data.available ? null : data.message ?? "Market map unavailable.");
        })
        .catch(() => {
          if (!cancelled && initial) setError("Failed to load the market map.");
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
  }, []);

  // recharts wants nested {name, children} with a numeric size key on leaves.
  const data = useMemo(
    () =>
      groups.map((g) => ({
        name: g.sector,
        children: g.items.map((it) => ({
          name: it.symbol,
          symbol: it.symbol,
          fullName: it.name,
          sector: g.sector,
          size: it.market_cap,
          change_pct: it.change_pct,
        })),
      })),
    [groups],
  );

  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-base font-semibold text-content">Market map</p>
          <p className="text-xs text-muted">
            S&amp;P mega-caps by sector — cell size = market cap, color = today&apos;s move
          </p>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-muted">
          <span>−3%</span>
          <span className="h-2 w-32 rounded-full" style={{
            background: "linear-gradient(to right, #f43f5e, #334155, #22c55e)",
          }} />
          <span>+3%</span>
        </div>
      </div>

      {loading ? (
        <p className="mt-4 text-sm text-faint">Building market map…</p>
      ) : error && groups.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{error}</p>
      ) : (
        <div className="mt-4 overflow-hidden rounded-lg bg-[#0b0f17] p-1">
          <div className="h-[520px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <Treemap
                data={data}
                dataKey="size"
                nameKey="name"
                stroke="#0b0f17"
                isAnimationActive={false}
                content={<Cell onSelect={(s) => router.push(`/dashboard/positions/${encodeURIComponent(s)}`)} />}
              >
                <Tooltip content={<CarpetTooltip />} />
              </Treemap>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
