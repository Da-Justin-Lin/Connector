"use client";

export interface FearGreed {
  score: number | null;
  rating: string | null;
  updated_at?: string | null;
  prev_close: number | null;
  prev_week?: number | null;
  prev_month?: number | null;
  prev_year?: number | null;
  available: boolean;
  message: string | null;
}

// CNN's five Fear & Greed bands. Order matters — used both to paint the gauge
// arc and to render the legend beneath it.
const RANGES = [
  { max: 25, label: "Extreme Fear", color: "#ef4444" },
  { max: 45, label: "Fear", color: "#f97316" },
  { max: 55, label: "Neutral", color: "#eab308" },
  { max: 75, label: "Greed", color: "#84cc16" },
  { max: 100, label: "Extreme Greed", color: "#10b981" },
] as const;

function rangeForScore(score: number) {
  return RANGES.find((r) => score < r.max) ?? RANGES[RANGES.length - 1];
}

function scoreColor(score: number) {
  return rangeForScore(score).color;
}

function Row({ label, value }: { label: string; value: number | null | undefined }) {
  const dotColor = value == null ? "#d1d5db" : scoreColor(value);
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted">{label}</span>
      <span className="flex items-center gap-1.5 font-medium text-content">
        <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: dotColor }} />
        {value == null ? "—" : Math.round(value)}
      </span>
    </div>
  );
}

interface FearGreedGaugeProps {
  fg: FearGreed;
  title?: string;
  source?: string;
}

// Semicircle gauge geometry — angle 0 maps to score 100 (right), PI to score 0 (left).
const RADIUS = 80;
const CX = 100;
const CY = 100;
const STROKE = 14;

function pointAt(pct: number, r: number = RADIUS) {
  const angle = Math.PI - pct * Math.PI;
  return { x: CX + r * Math.cos(angle), y: CY - r * Math.sin(angle) };
}

function arcPath(fromPct: number, toPct: number, r: number = RADIUS) {
  const a = pointAt(fromPct, r);
  const b = pointAt(toPct, r);
  return `M ${a.x} ${a.y} A ${r} ${r} 0 0 1 ${b.x} ${b.y}`;
}

export default function FearGreedGauge({ fg, title = "Fear & Greed", source = "CNN" }: FearGreedGaugeProps) {
  const score = fg.score;
  const color = score == null ? "#9ca3af" : scoreColor(score);
  const activeLabel = score == null ? null : rangeForScore(score).label;

  // Only show comparison rows that have a value (crypto feed has just one).
  const comparisons = [
    { label: "Previous close", value: fg.prev_close },
    { label: "1 week ago", value: fg.prev_week },
    { label: "1 month ago", value: fg.prev_month },
    { label: "1 year ago", value: fg.prev_year },
  ].filter((c) => c.value != null);

  const needleTip = score == null ? pointAt(0.5, RADIUS - 22) : pointAt(score / 100, RADIUS - 22);
  let prevMax = 0;

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-content">{title}</p>
        <span className="text-xs text-faint">{source}</span>
      </div>

      {!fg.available || score == null ? (
        <p className="mt-6 text-center text-sm text-faint">
          {fg.message ?? "Unavailable right now."}
        </p>
      ) : (
        <>
          <div className="mt-2 flex flex-col items-center">
            <svg viewBox="0 0 200 118" className="w-full max-w-[260px]">
              <defs>
                <filter id="fgNeedleShadow" x="-50%" y="-50%" width="200%" height="200%">
                  <feDropShadow dx="0" dy="1" stdDeviation="1.2" floodColor="#000" floodOpacity="0.25" />
                </filter>
              </defs>

              {/* Colored bands for each sentiment range */}
              {RANGES.map((r, i) => {
                const fromPct = prevMax / 100;
                const toPct = r.max / 100;
                prevMax = r.max;
                return (
                  <path
                    key={r.label}
                    d={arcPath(fromPct, toPct)}
                    fill="none"
                    stroke={r.color}
                    strokeWidth={STROKE}
                    strokeLinecap={i === 0 || i === RANGES.length - 1 ? "round" : "butt"}
                    opacity={activeLabel === r.label ? 1 : 0.35}
                  />
                );
              })}

              {/* Tick marks at band boundaries */}
              {[0, 25, 45, 55, 75, 100].map((t) => {
                const inner = pointAt(t / 100, RADIUS - STROKE / 2 - 3);
                const outer = pointAt(t / 100, RADIUS + STROKE / 2 + 3);
                return (
                  <line
                    key={t}
                    x1={inner.x}
                    y1={inner.y}
                    x2={outer.x}
                    y2={outer.y}
                    stroke="#ffffff"
                    strokeWidth={1.5}
                  />
                );
              })}

              {/* Needle */}
              <line
                x1={CX}
                y1={CY}
                x2={needleTip.x}
                y2={needleTip.y}
                stroke="#374151"
                strokeWidth={2.5}
                strokeLinecap="round"
                filter="url(#fgNeedleShadow)"
              />
              <circle cx={CX} cy={CY} r="7" fill="#ffffff" stroke={color} strokeWidth={3} filter="url(#fgNeedleShadow)" />

              {/* End labels */}
              <text x={pointAt(0).x} y={pointAt(0).y + 14} textAnchor="start" fontSize={8} fill="#9ca3af">
                0
              </text>
              <text x={pointAt(1).x} y={pointAt(1).y + 14} textAnchor="end" fontSize={8} fill="#9ca3af">
                100
              </text>
            </svg>

            <p className="-mt-5 text-3xl font-bold" style={{ color }}>
              {Math.round(score)}
            </p>
            <p
              className="mt-0.5 rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize"
              style={{ color, background: `${color}1a` }}
            >
              {fg.rating ?? activeLabel ?? ""}
            </p>
          </div>

          {/* Range legend — current band highlighted */}
          <div className="mt-4 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-t border-line/60 pt-3">
            {RANGES.map((r) => (
              <span
                key={r.label}
                className="flex items-center gap-1 text-[10px] font-medium"
                style={{ color: activeLabel === r.label ? r.color : "#9ca3af" }}
              >
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ background: r.color, opacity: activeLabel === r.label ? 1 : 0.4 }}
                />
                {r.label}
              </span>
            ))}
          </div>

          {comparisons.length > 0 && (
            <div className="mt-3 space-y-1 border-t border-line/60 pt-3">
              {comparisons.map((c) => (
                <Row key={c.label} label={c.label} value={c.value} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
