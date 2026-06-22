// Chart overlay indicators. Like the drawing-tool registry, INDICATORS is the
// single source of truth: the "add indicator" menu, the line-series manager,
// and the legend all read from it, so a new indicator is one more entry.

export interface Indicator {
  id: string;
  type: string;
  period: number;
  color: string;
}

export interface IndicatorDef {
  type: string;
  /** Long label for the add menu. */
  label: string;
  /** Short label for the active-indicator chip. */
  short: string;
  defaultPeriod: number;
  /** Value per candle, aligned to the input; null until enough history. */
  compute: (closes: number[], period: number) => Array<number | null>;
}

function sma(closes: number[], period: number): Array<number | null> {
  const out: Array<number | null> = new Array(closes.length).fill(null);
  if (period < 1) return out;
  let sum = 0;
  for (let i = 0; i < closes.length; i++) {
    sum += closes[i];
    if (i >= period) sum -= closes[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

function ema(closes: number[], period: number): Array<number | null> {
  const out: Array<number | null> = new Array(closes.length).fill(null);
  if (period < 1 || closes.length < period) return out;
  const k = 2 / (period + 1);
  let prev = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = prev;
  for (let i = period; i < closes.length; i++) {
    prev = closes[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

export const INDICATORS: IndicatorDef[] = [
  { type: "sma", label: "Moving Average (SMA)", short: "SMA", defaultPeriod: 50, compute: sma },
  { type: "ema", label: "Moving Average (EMA)", short: "EMA", defaultPeriod: 50, compute: ema },
];

export const INDICATOR_MAP: Record<string, IndicatorDef> = Object.fromEntries(
  INDICATORS.map((d) => [d.type, d]),
);

// Colors cycled as indicators are added.
export const INDICATOR_COLORS = ["#f59e0b", "#3b82f6", "#a855f7", "#22c55e", "#ef4444", "#14b8a6"];
