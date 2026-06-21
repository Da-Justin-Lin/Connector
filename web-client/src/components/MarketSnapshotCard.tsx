"use client";

import {
  AreaSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

export interface Candle {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface Snapshot {
  symbol: string;
  candles: Candle[];
  last_price: number | null;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
}

const LABELS: Record<string, string> = {
  SPY: "S&P 500",
  QQQ: "Nasdaq 100",
  DIA: "Dow Jones",
  IWM: "Russell 2000",
  "BTC-USD": "Bitcoin",
  "ETH-USD": "Ethereum",
  GLD: "Gold",
  "^VIX": "Volatility (VIX)",
};

function fmtPrice(n: number | null) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(rate: number | null) {
  if (rate == null) return "—";
  const pct = rate * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

export default function MarketSnapshotCard({ snap }: { snap: Snapshot }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  const up = (snap.change ?? 0) >= 0;
  const lineColor = up ? "#10b981" : "#ef4444";
  const topColor = up ? "rgba(16,185,129,0.20)" : "rgba(239,68,68,0.20)";

  // Create the chart once.
  useEffect(() => {
    if (!hostRef.current) return;
    const chart = createChart(hostRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#9ca3af",
        fontSize: 10,
      },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { visible: false },
      leftPriceScale: { visible: false },
      timeScale: { visible: false, borderVisible: false },
      handleScroll: false,
      handleScale: false,
      crosshair: { horzLine: { visible: false }, vertLine: { visible: false } },
      autoSize: true,
    });
    const series = chart.addSeries(AreaSeries, {
      lineColor,
      topColor,
      bottomColor: "rgba(255,255,255,0)",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Recolor when direction flips.
  useEffect(() => {
    seriesRef.current?.applyOptions({ lineColor, topColor });
  }, [lineColor, topColor]);

  // Push candle data.
  useEffect(() => {
    if (!seriesRef.current) return;
    const points = snap.candles.map((c) => ({ time: c.t as Time, value: c.c }));
    seriesRef.current.setData(points);
    if (points.length > 0) chartRef.current?.timeScale().fitContent();
  }, [snap.candles]);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-semibold text-gray-900">{snap.symbol}</p>
          <p className="text-xs text-gray-500">{LABELS[snap.symbol] ?? ""}</p>
        </div>
        <div className="text-right">
          <p className="text-lg font-bold text-gray-900">{fmtPrice(snap.last_price)}</p>
          <p className={`text-xs font-medium ${up ? "text-emerald-600" : "text-rose-600"}`}>
            {snap.change == null ? "—" : `${up ? "+" : "−"}${fmtPrice(Math.abs(snap.change))}`}{" "}
            ({fmtPct(snap.change_pct)})
          </p>
        </div>
      </div>
      <div className="relative mt-3 h-28">
        <div ref={hostRef} className="absolute inset-0" />
        {snap.candles.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-gray-400">
            No intraday data
          </div>
        )}
      </div>
    </div>
  );
}
