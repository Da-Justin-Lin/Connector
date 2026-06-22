"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { useThemeColors } from "@/hooks/useThemeColors";
import api from "@/services/api";
import ChartToolbox from "./chart/ChartToolbox";
import { DrawingsPrimitive } from "./chart/DrawingsPrimitive";
import {
  DEFAULT_DRAW_COLOR,
  DRAWING_TOOLS,
  TOOL_MAP,
  type Drawing,
  type DrawingPoint,
} from "./chart/drawingTools";

export type Range = "1D" | "1W" | "1M" | "3M" | "1Y" | "5Y" | "MAX";

const RANGES: Range[] = ["1D", "1W", "1M", "3M", "1Y", "5Y", "MAX"];

type IntervalChoice = "AUTO" | "30M" | "1D" | "1W";

const INTERVAL_OPTIONS: { value: IntervalChoice; label: string }[] = [
  { value: "AUTO", label: "Auto" },
  { value: "30M", label: "30 min" },
  { value: "1D", label: "Daily" },
  { value: "1W", label: "Weekly" },
];

// yfinance interval string (from the response) -> friendly label.
const INTERVAL_LABEL: Record<string, string> = {
  "5m": "5-min",
  "30m": "30-min",
  "1h": "hourly",
  "1d": "daily",
  "1wk": "weekly",
};

// How often to silently re-fetch in the background (ms)
const POLL_INTERVAL: Record<Range, number> = {
  "1D": 30_000,
  "1W": 60_000,
  "1M": 5 * 60_000,
  "3M": 5 * 60_000,
  "1Y": 5 * 60_000,
  "5Y": 5 * 60_000,
  "MAX": 5 * 60_000,
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
  interval?: string | null;
}

interface PriceChartProps {
  symbol: string;
  initialRange?: Range;
  // Reports the latest close + refresh time so a parent can show a header price.
  onLatest?: (close: number | null, updatedAt: Date) => void;
}

export default function PriceChart({ symbol, initialRange = "1M", onLatest }: PriceChartProps) {
  const [range, setRange] = useState<Range>(initialRange);
  const [intervalChoice, setIntervalChoice] = useState<IntervalChoice>("AUTO");
  const [data, setData] = useState<CandlesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const c = useThemeColors();

  const [activeTool, setActiveTool] = useState("cursor");
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [activeColor, setActiveColor] = useState(DEFAULT_DRAW_COLOR);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const chartHostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const onLatestRef = useRef(onLatest);
  onLatestRef.current = onLatest;

  // Drawing state machine lives in refs so the once-subscribed chart handlers
  // always read the latest values without re-subscribing on every render.
  const primitiveRef = useRef<DrawingsPrimitive | null>(null);
  const activeToolRef = useRef(activeTool);
  activeToolRef.current = activeTool;
  const activeColorRef = useRef(activeColor);
  activeColorRef.current = activeColor;
  const selectedIdRef = useRef(selectedId);
  selectedIdRef.current = selectedId;
  const symbolRef = useRef(symbol);
  symbolRef.current = symbol;
  const pendingRef = useRef<DrawingPoint[]>([]);
  const drawingsRef = useRef<Drawing[]>([]);
  const dragRef = useRef<{
    id: string;
    anchorIndex: number | null;
    lastX: number;
    lastY: number;
    moved: boolean;
  } | null>(null);

  const storageKey = (s: string) => `chart-drawings:${s.toUpperCase()}`;

  // Single write path for drawings: updates React state, the primitive, the
  // ref mirror, and localStorage (under the current symbol) in lockstep.
  const commitDrawings = (updater: (prev: Drawing[]) => Drawing[]) => {
    setDrawings((prev) => {
      const next = updater(prev);
      drawingsRef.current = next;
      primitiveRef.current?.setDrawings(next);
      try {
        localStorage.setItem(storageKey(symbolRef.current), JSON.stringify(next));
      } catch {
        /* ignore quota / serialization errors */
      }
      return next;
    });
  };

  const emitLatest = (resp: CandlesResponse) => {
    const close = resp.candles.length > 0 ? resp.candles[resp.candles.length - 1].c : null;
    onLatestRef.current?.(close, new Date());
  };

  const candlesUrl = `/api/v1/market/candles?symbol=${encodeURIComponent(
    symbol,
  )}&range=${range}&interval=${intervalChoice}`;

  // Initial fetch (shows loading spinner)
  useEffect(() => {
    setLoading(true);
    setData(null);
    api
      .get<CandlesResponse>(candlesUrl)
      .then(({ data }) => {
        setData(data);
        emitLatest(data);
      })
      .catch(() =>
        setData({ symbol, range, candles: [], available: false, message: "Failed to load market data." }),
      )
      .finally(() => setLoading(false));
  }, [symbol, range, intervalChoice]);

  // Background polling — silently refreshes without touching loading state
  useEffect(() => {
    const id = setInterval(() => {
      api
        .get<CandlesResponse>(candlesUrl)
        .then(({ data }) => {
          setData(data);
          emitLatest(data);
        })
        .catch(() => {});
    }, POLL_INTERVAL[range]);
    return () => clearInterval(id);
  }, [symbol, range, intervalChoice]);

  // Create chart once
  useEffect(() => {
    if (!chartHostRef.current) return;
    const chart = createChart(chartHostRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9ca3af",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "rgba(148,163,184,0.12)" },
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

    // Attach the drawings layer and the click/anchor state machine.
    const primitive = new DrawingsPrimitive();
    series.attachPrimitive(primitive);
    primitiveRef.current = primitive;

    const paramToPoint = (param: MouseEventParams): DrawingPoint | null => {
      if (!param.point) return null;
      const price = series.coordinateToPrice(param.point.y);
      const time = param.time ?? chart.timeScale().coordinateToTime(param.point.x) ?? undefined;
      if (price == null || time == null) return null;
      return { time, price };
    };

    const handleClick = (param: MouseEventParams) => {
      const tool = TOOL_MAP[activeToolRef.current];
      if (!tool || tool.anchors === 0) return;
      const pt = paramToPoint(param);
      if (!pt) return;
      const next = [...pendingRef.current, pt];
      if (next.length >= tool.anchors) {
        const drawing: Drawing = {
          id: `d${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          toolId: tool.id,
          points: next,
          color: activeColorRef.current,
        };
        pendingRef.current = [];
        primitive.setPreview(null);
        commitDrawings((prev) => [...prev, drawing]);
        setActiveTool("cursor"); // revert to cursor after each completed drawing
        setSelectedId(drawing.id); // select it so it can be recolored/moved
      } else {
        pendingRef.current = next;
      }
    };

    // Rubber-band the in-progress drawing under the crosshair.
    const handleMove = (param: MouseEventParams) => {
      if (pendingRef.current.length === 0) return;
      const tool = TOOL_MAP[activeToolRef.current];
      if (!tool) return;
      const pt = paramToPoint(param);
      if (!pt) {
        primitive.setPreview(null);
        return;
      }
      primitive.setPreview({
        id: "preview",
        toolId: tool.id,
        points: [...pendingRef.current, pt],
        color: activeColorRef.current,
      });
    };

    chart.subscribeClick(handleClick);
    chart.subscribeCrosshairMove(handleMove);

    // --- select & drag (cursor tool only) ---------------------------------- #
    const host = chartHostRef.current!; // non-null: the effect returned above if absent
    const relative = (e: MouseEvent) => {
      const rect = host.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    };

    const onDown = (e: MouseEvent) => {
      if (activeToolRef.current !== "cursor") return;
      const { x, y } = relative(e);
      const hit = primitive.pick(x, y);
      if (!hit) {
        setSelectedId(null);
        return;
      }
      setSelectedId(hit.id);
      const d = drawingsRef.current.find((dd) => dd.id === hit.id);
      if (d) setActiveColor(d.color);
      dragRef.current = { id: hit.id, anchorIndex: hit.anchorIndex, lastX: x, lastY: y, moved: false };
      // Suspend chart pan/zoom while dragging a drawing.
      chart.applyOptions({ handleScroll: false, handleScale: false });
    };

    const onMove = (e: MouseEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const { x, y } = relative(e);
      const dx = x - drag.lastX;
      const dy = y - drag.lastY;
      drag.lastX = x;
      drag.lastY = y;
      drag.moved = true;
      const ts = chart.timeScale();
      commitDrawings((prev) =>
        prev.map((d) => {
          if (d.id !== drag.id) return d;
          if (drag.anchorIndex != null) {
            const price = series.coordinateToPrice(y);
            const time = ts.coordinateToTime(x);
            if (price == null || time == null) return d;
            const points = d.points.slice();
            points[drag.anchorIndex] = { time, price };
            return { ...d, points };
          }
          // Body move: shift every anchor by the pixel delta, then re-project.
          const points = d.points.map((p) => {
            const px = ts.timeToCoordinate(p.time);
            const py = series.priceToCoordinate(p.price);
            if (px == null || py == null) return p;
            const time = ts.coordinateToTime(px + dx);
            const price = series.coordinateToPrice(py + dy);
            return time == null || price == null ? p : { time, price };
          });
          return { ...d, points };
        }),
      );
    };

    const onUp = () => {
      if (!dragRef.current) return;
      dragRef.current = null;
      chart.applyOptions({ handleScroll: true, handleScale: true });
    };

    host.addEventListener("mousedown", onDown, true);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);

    return () => {
      chart.unsubscribeClick(handleClick);
      chart.unsubscribeCrosshairMove(handleMove);
      host.removeEventListener("mousedown", onDown, true);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      primitiveRef.current = null;
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Mirror selection into the primitive so the selected drawing shows handles.
  useEffect(() => {
    primitiveRef.current?.setSelected(selectedId);
  }, [selectedId]);

  // Load this symbol's saved drawings (and reset transient state) on switch.
  useEffect(() => {
    pendingRef.current = [];
    primitiveRef.current?.setPreview(null);
    setActiveTool("cursor");
    setSelectedId(null);
    let loaded: Drawing[] = [];
    try {
      const raw = localStorage.getItem(storageKey(symbol));
      if (raw) loaded = JSON.parse(raw) as Drawing[];
    } catch {
      loaded = [];
    }
    drawingsRef.current = loaded;
    setDrawings(loaded);
    primitiveRef.current?.setDrawings(loaded);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  // Escape cancels a pending drawing / deselects; Delete removes the selection.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (e.key === "Escape") {
        pendingRef.current = [];
        primitiveRef.current?.setPreview(null);
        setActiveTool("cursor");
        setSelectedId(null);
      } else if ((e.key === "Delete" || e.key === "Backspace") && selectedIdRef.current) {
        e.preventDefault();
        const id = selectedIdRef.current;
        setSelectedId(null);
        commitDrawings((prev) => prev.filter((d) => d.id !== id));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-theme the chart (text/grid/candle colors) when the theme flips.
  useEffect(() => {
    chartRef.current?.applyOptions({
      layout: { textColor: c.muted },
      grid: { horzLines: { color: c.line } },
    });
    seriesRef.current?.applyOptions({
      upColor: c.up,
      downColor: c.down,
      wickUpColor: c.up,
      wickDownColor: c.down,
    });
  }, [c]);

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

  const undoDrawing = () => commitDrawings((prev) => prev.slice(0, -1));
  const clearDrawings = () => {
    pendingRef.current = [];
    primitiveRef.current?.setPreview(null);
    setSelectedId(null);
    commitDrawings(() => []);
  };
  const deleteSelected = () => {
    const id = selectedIdRef.current;
    if (!id) return;
    setSelectedId(null);
    commitDrawings((prev) => prev.filter((d) => d.id !== id));
  };
  // Set the color for new drawings; if one is selected, recolor it too.
  const handleColorChange = (color: string) => {
    setActiveColor(color);
    const id = selectedIdRef.current;
    if (id) commitDrawings((prev) => prev.map((d) => (d.id === id ? { ...d, color } : d)));
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <select
            value={intervalChoice}
            onChange={(e) => setIntervalChoice(e.target.value as IntervalChoice)}
            className="tap rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-xs font-medium text-content focus:outline-none focus:ring-1 focus:ring-brand"
          >
            {INTERVAL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          {data?.interval && INTERVAL_LABEL[data.interval] && (
            <span className="text-xs text-muted">{INTERVAL_LABEL[data.interval]} candles</span>
          )}
        </div>
        <div className="flex gap-1 rounded-lg bg-surface-2 p-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`tap rounded-md px-3 py-1 text-xs font-medium transition-colors ${
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
        <div className="absolute left-2 top-2 z-10">
          <ChartToolbox
            tools={DRAWING_TOOLS}
            activeTool={activeTool}
            onSelect={(id) => {
              setSelectedId(null);
              setActiveTool(id);
            }}
            color={activeColor}
            onColorChange={handleColorChange}
            onDelete={deleteSelected}
            hasSelection={selectedId !== null}
            onUndo={undoDrawing}
            onClear={clearDrawings}
            hasDrawings={drawings.length > 0}
          />
        </div>
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
