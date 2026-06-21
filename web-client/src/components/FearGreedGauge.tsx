"use client";

export interface FearGreed {
  score: number | null;
  rating: string | null;
  updated_at: string | null;
  prev_close: number | null;
  prev_week: number | null;
  prev_month: number | null;
  prev_year: number | null;
  available: boolean;
  message: string | null;
}

// Maps a 0–100 score to a color along red → amber → green.
function scoreColor(score: number) {
  if (score < 25) return "#ef4444"; // extreme fear
  if (score < 45) return "#f97316"; // fear
  if (score < 55) return "#eab308"; // neutral
  if (score < 75) return "#84cc16"; // greed
  return "#10b981"; // extreme greed
}

function Row({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-gray-700">{value == null ? "—" : Math.round(value)}</span>
    </div>
  );
}

export default function FearGreedGauge({ fg }: { fg: FearGreed }) {
  const score = fg.score;

  // Semicircle gauge geometry.
  const radius = 80;
  const cx = 100;
  const cy = 100;
  const angle = score == null ? 0 : Math.PI - (score / 100) * Math.PI;
  const nx = cx + radius * Math.cos(angle);
  const ny = cy - radius * Math.sin(angle);
  const color = score == null ? "#9ca3af" : scoreColor(score);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-900">Fear &amp; Greed</p>
        <span className="text-xs text-gray-400">CNN</span>
      </div>

      {!fg.available || score == null ? (
        <p className="mt-6 text-center text-sm text-gray-400">
          {fg.message ?? "Unavailable right now."}
        </p>
      ) : (
        <>
          <div className="mt-2 flex flex-col items-center">
            <svg viewBox="0 0 200 120" className="w-full max-w-[220px]">
              {/* Track */}
              <path
                d="M 20 100 A 80 80 0 0 1 180 100"
                fill="none"
                stroke="#e5e7eb"
                strokeWidth="12"
                strokeLinecap="round"
              />
              {/* Needle */}
              <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={color} strokeWidth="3" strokeLinecap="round" />
              <circle cx={cx} cy={cy} r="5" fill={color} />
            </svg>
            <p className="-mt-4 text-3xl font-bold" style={{ color }}>
              {Math.round(score)}
            </p>
            <p className="text-sm font-medium capitalize" style={{ color }}>
              {fg.rating ?? ""}
            </p>
          </div>

          <div className="mt-4 space-y-1 border-t border-gray-100 pt-3">
            <Row label="Previous close" value={fg.prev_close} />
            <Row label="1 week ago" value={fg.prev_week} />
            <Row label="1 month ago" value={fg.prev_month} />
            <Row label="1 year ago" value={fg.prev_year} />
          </div>
        </>
      )}
    </div>
  );
}
