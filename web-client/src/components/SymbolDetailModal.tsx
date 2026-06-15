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

type Range = "1D" | "1W" | "1M" | "3M" | "1Y";

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

interface SymbolDetailModalProps {
  symbol: string;
  name: string | null;
  onClose: () => void;
}

export default function SymbolDetailModal({ symbol, name, onClose }: SymbolDetailModalProps) {
  const [range, setRange] = useState<Range>("1M");
  const [data, setData] = useState<CandlesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const chartHostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  // Esc to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Initial fetch (shows loading spinner)
  useEffect(() => {
    setLoading(true);
    setData(null);
    api
      .get<CandlesResponse>(`/api/v1/market/candles?symbol=${encodeURIComponent(symbol)}&range=${range}`)
      .then(({ data }) => { setData(data); setLastUpdated(new Date()); })
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
        .then(({ data }) => { setData(data); setLastUpdated(new Date()); })
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

  const latestClose = data && data.candles.length > 0 ? data.candles[data.candles.length - 1].c : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex h-[80vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <p className="text-lg font-bold text-gray-900">{symbol}</p>
            <p className="text-xs text-gray-500">{name ?? "—"}</p>
            {latestClose !== null && (
              <p className="mt-1 text-base font-semibold text-gray-900">
                ${latestClose.toFixed(2)}
              </p>
            )}
            {lastUpdated && (
              <p className="mt-0.5 text-xs text-gray-400">
                Updated {lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
              {RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                    range === r
                      ? "bg-white text-gray-900 shadow-sm"
                      : "text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
              aria-label="Close"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
                className="h-5 w-5"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
        <div className="relative flex-1">
          <div ref={chartHostRef} className="absolute inset-0" />
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/70 text-sm text-gray-400">
              Loading…
            </div>
          )}
          {!loading && data && !data.available && (
            <div className="absolute inset-0 flex items-center justify-center bg-white text-center text-sm text-gray-500">
              {data.message ?? "Market data unavailable."}
            </div>
          )}
          {!loading && data && data.available && data.candles.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center bg-white text-center text-sm text-gray-500">
              {data.message ?? "No candle data in this range."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
