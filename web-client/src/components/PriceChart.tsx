"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import api from "@/services/api";

export type Range = "1D" | "1W" | "1M" | "3M" | "1Y";

const RANGES: Range[] = ["1D", "1W", "1M", "3M", "1Y"];

// How often to silently re-fetch in the background (ms)
const POLL_INTERVAL: Record<Range, number> = {
  "1D": 30_000,
  "1W": 60_000,
  "1M": 5 * 60_000,
  "3M": 5 * 60_000,
  "1Y": 5 * 60_000,
};

interface Candle {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

interface CandlesResponse {
  symbol: string;
  range: string;
  candles: Candle[];
  available: boolean;
  message: string | null;
}

interface PriceChartProps {
  symbol: string;
  initialRange?: Range;
  // Reports the latest close + refresh time so a parent can show a header price.
  onLatest?: (close: number | null, updatedAt: Date) => void;
}

export default function PriceChart({ symbol, initialRange = "1M", onLatest }: PriceChartProps) {
  const [range, setRange] = useState<Range>(initialRange);
  const [data, setData] = useState<CandlesResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const chartHostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const onLatestRef = useRef(onLatest);
  onLatestRef.current = onLatest;

  const emitLatest = (resp: CandlesResponse) => {
    const close = resp.candles.length > 0 ? resp.candles[resp.candles.length - 1].c : null;
    onLatestRef.current?.(close, new Date());
  };

  // Initial fetch (shows loading spinner)
  useEffect(() => {
    setLoading(true);
    setData(null);
    api
      .get<CandlesResponse>(`/api/v1/market/candles?symbol=${encodeURIComponent(symbol)}&range=${range}`)
      .then(({ data }) => {
        setData(data);
        emitLatest(data);
      })
      .catch(() =>
        setData({ symbol, range, candles: [], available: false, message: "Failed to load market data." }),
      )
      .finally(() => setLoading(false));
  }, [symbol, range]);

  // Background polling — silently refreshes without touching loading state
  useEffect(() => {
    const id = setInterval(() => {
      api
        .get<CandlesResponse>(`/api/v1/market/candles?symbol=${encodeURIComponent(symbol)}&range=${range}`)
        .then(({ data }) => {
          setData(data);
          emitLatest(data);
        })
        .catch(() => {});
    }, POLL_INTERVAL[range]);
    return () => clearInterval(id);
  }, [symbol, range]);

  // Create chart once
  useEffect(() => {
    if (!chartHostRef.current) return;
    const chart = createChart(chartHostRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#374151",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#f3f4f6" },
        horzLines: { color: "#f3f4f6" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false },
      autoSize: true,
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Push data into series whenever it updates
  useEffect(() => {
    if (!seriesRef.current || !data) return;
    const points = data.candles.map((c) => ({
      time: c.t as Time,
      open: c.o,
      high: c.h,
      low: c.l,
      close: c.c,
    }));
    seriesRef.current.setData(points);
    if (points.length > 0) {
      chartRef.current?.timeScale().fitContent();
    }
  }, [data]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex justify-end">
        <div className="flex gap-1 rounded-lg bg-surface-2 p-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                range === r
                  ? "bg-surface text-content shadow-sm"
                  : "text-muted hover:text-content"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      <div className="relative mt-2 flex-1">
        <div ref={chartHostRef} className="absolute inset-0" />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface/70 text-sm text-faint">
            Loading…
          </div>
        )}
        {!loading && data && !data.available && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface text-center text-sm text-muted">
            {data.message ?? "Market data unavailable."}
          </div>
        )}
        {!loading && data && data.available && data.candles.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface text-center text-sm text-muted">
            {data.message ?? "No candle data in this range."}
          </div>
        )}
      </div>
    </div>
  );
}
