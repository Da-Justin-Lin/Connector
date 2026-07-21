"use client";

import { useEffect, useRef, useState } from "react";

import api from "@/services/api";

interface ExitAlert {
  id: string;
  signal: string;
  confidence: string;
  price: number;
  stop_loss: number | null;
  target_price: number | null;
  reasoning: string | null;
  created_at: string;
}

interface Position {
  id: string;
  ticker: string;
  shares: number;
  entry_price: number;
  entry_date: string;
  initial_stop: number;
  target: number;
  status: string;
  notes: string | null;
  source_signal_id: string | null;
  exit_price: number | null;
  exit_reason: string | null;
  opened_at: string;
  closed_at: string | null;
  alerts: ExitAlert[];
}

interface PositionsResponse {
  positions: Position[];
}

const POLL_MS = 60_000;

function fmt(n: number | null | undefined) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function alertClasses(sig: string) {
  if (sig === "TARGET_HIT") return "bg-up/10 text-up border-up/30";
  if (sig === "HARD_STOP") return "bg-down/10 text-down border-down/30";
  if (sig === "TRAIL_RAISED") return "bg-brand/10 text-brand border-brand/30";
  return "bg-surface-2 text-muted border-line";
}

export default function TradesPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"OPEN" | "CLOSED">("OPEN");
  const tabRef = useRef(tab);
  tabRef.current = tab;

  const load = () => {
    api
      .get<PositionsResponse>(`/api/v1/positions?status=${tabRef.current}`)
      .then((res) => {
        setPositions(res.data.positions);
        setError(null);
      })
      .catch(() => setError("Failed to load positions."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setLoading(true);
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const close = async (p: Position) => {
    const raw = prompt(`Close ${p.ticker} — exit price?`, String(p.alerts[0]?.price ?? p.entry_price));
    if (raw == null) return;
    const exit = Number(raw);
    if (!exit || exit <= 0) {
      setError("Exit price must be greater than zero.");
      return;
    }
    try {
      await api.post(`/api/v1/positions/${p.id}/close`, { exit_price: exit, exit_reason: "manual" });
      load();
    } catch {
      setError("Failed to close position.");
    }
  };

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="bg-brand bg-clip-text text-2xl font-bold tracking-tight text-transparent">
            Trades
          </h1>
          <p className="mt-1 text-sm text-muted">
            Positions you confirmed from signals. Exit alerts land under the exact trade.
          </p>
        </div>
        <div className="flex gap-1 rounded-full border border-line bg-surface p-1">
          {(["OPEN", "CLOSED"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`tap rounded-full px-4 py-1 text-xs font-medium transition-colors ${
                tab === t ? "bg-brand/10 text-content" : "text-muted hover:text-content"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-down">{error}</p>}

      {loading ? (
        <p className="px-6 py-8 text-center text-sm text-faint">Loading…</p>
      ) : positions.length === 0 ? (
        <div className="card px-6 py-12 text-center">
          <p className="text-sm text-muted">No {tab.toLowerCase()} trades.</p>
          {tab === "OPEN" && (
            <p className="mt-1 text-xs text-faint">
              Click “I took this trade” on a BUY signal to start tracking one.
            </p>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {positions.map((p) => {
            const realized =
              p.exit_price != null ? (p.exit_price - p.entry_price) * p.shares : null;
            return (
              <div key={p.id} className="card p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-bold text-content">{p.ticker}</p>
                    <p className="text-xs text-faint">
                      {fmt(p.shares)} sh · opened {fmtTime(p.opened_at)}
                    </p>
                  </div>
                  {p.status === "OPEN" ? (
                    <button
                      onClick={() => close(p)}
                      className="tap rounded-md border border-line px-3 py-1.5 text-xs font-medium text-content hover:bg-surface-2"
                    >
                      I sold — close
                    </button>
                  ) : (
                    <div className="text-right">
                      <p className="text-[10px] uppercase tracking-wide text-faint">Realized</p>
                      <p
                        className={`num text-sm font-bold ${
                          (realized ?? 0) >= 0 ? "text-up" : "text-down"
                        }`}
                      >
                        {realized == null ? "—" : `${realized >= 0 ? "+" : ""}$${fmt(realized)}`}
                      </p>
                    </div>
                  )}
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
                  <div className="rounded-md bg-surface-2 py-2">
                    <p className="text-[10px] uppercase tracking-wide text-faint">Entry</p>
                    <p className="num text-sm font-semibold text-content">${fmt(p.entry_price)}</p>
                  </div>
                  <div className="rounded-md bg-surface-2 py-2">
                    <p className="text-[10px] uppercase tracking-wide text-faint">Stop</p>
                    <p className="num text-sm font-semibold text-down">${fmt(p.initial_stop)}</p>
                  </div>
                  <div className="rounded-md bg-surface-2 py-2">
                    <p className="text-[10px] uppercase tracking-wide text-faint">Target</p>
                    <p className="num text-sm font-semibold text-up">${fmt(p.target)}</p>
                  </div>
                  <div className="rounded-md bg-surface-2 py-2">
                    <p className="text-[10px] uppercase tracking-wide text-faint">
                      {p.status === "OPEN" ? "Status" : "Exit"}
                    </p>
                    <p className="num text-sm font-semibold text-content">
                      {p.status === "OPEN" ? "OPEN" : `$${fmt(p.exit_price)}`}
                    </p>
                  </div>
                </div>

                {p.alerts.length > 0 && (
                  <div className="mt-4 border-t border-line pt-3">
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted">
                      Exit alerts
                    </p>
                    <div className="flex flex-col gap-2">
                      {p.alerts.map((a) => (
                        <div key={a.id} className="flex items-start gap-2">
                          <span
                            className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-bold ${alertClasses(a.signal)}`}
                          >
                            {a.signal.replace(/_/g, " ")}
                          </span>
                          <div className="min-w-0">
                            <p className="text-xs text-content">{a.reasoning}</p>
                            <p className="text-[10px] text-faint">{fmtTime(a.created_at)}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
