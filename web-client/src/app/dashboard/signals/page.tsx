"use client";

import { useEffect, useRef, useState } from "react";

import api from "@/services/api";

interface TradingSignal {
  id: string;
  ticker: string;
  signal: string;
  confidence: string;
  price: number;
  entry_price: number | null;
  target_price: number | null;
  stop_loss: number | null;
  shares: number | null;
  score: number | null;
  max_score: number | null;
  risk_reward_ratio: number | null;
  regime: string | null;
  order_status: string | null;
  reasoning: string | null;
  exit_plan: string | null;
  created_at: string;
}

interface SignalsResponse {
  signals: TradingSignal[];
}

const POLL_MS = 60_000;

function fmt(n: number | null | undefined) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function signalClasses(sig: string) {
  // Entry BUY + profit-side exit alerts read green; stop-outs red; trail info blue.
  if (sig === "BUY" || sig === "TARGET_HIT") return "bg-up/10 text-up border-up/30";
  if (sig === "SELL" || sig === "HARD_STOP") return "bg-down/10 text-down border-down/30";
  if (sig === "TRAIL_RAISED") return "bg-brand/10 text-brand border-brand/30";
  return "bg-surface-2 text-muted border-line"; // HOLD / THESIS_BROKEN / TIME_STOP / REGIME_SHIFT
}

function signalLabel(sig: string) {
  return sig.replace(/_/g, " ");
}

const FILTERS = ["ALL", "BUY", "SELL"] as const;
type Filter = (typeof FILTERS)[number];

export default function SignalsPage() {
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("ALL");
  const filterRef = useRef<Filter>(filter);
  filterRef.current = filter;

  // "I took this trade" inline form state, keyed by the signal being confirmed.
  const [takingId, setTakingId] = useState<string | null>(null);
  const [form, setForm] = useState({ shares: "", entry: "", stop: "", target: "" });
  const [takeMsg, setTakeMsg] = useState<string | null>(null);
  const [taking, setTaking] = useState(false);

  const openTake = (s: TradingSignal) => {
    setTakeMsg(null);
    setForm({
      shares: s.shares != null ? String(s.shares) : "",
      entry: s.entry_price != null ? String(s.entry_price) : String(s.price),
      stop: s.stop_loss != null ? String(s.stop_loss) : "",
      target: s.target_price != null ? String(s.target_price) : "",
    });
    setTakingId(s.id);
  };

  const submitTake = async (s: TradingSignal) => {
    const shares = Number(form.shares);
    const entry = Number(form.entry);
    const stop = Number(form.stop);
    const target = Number(form.target);
    if (!shares || !entry || !stop || !target) {
      setTakeMsg("Fill in shares, entry, stop and target.");
      return;
    }
    setTaking(true);
    setTakeMsg(null);
    try {
      await api.post("/api/v1/positions", {
        ticker: s.ticker,
        shares,
        entry_price: entry,
        initial_stop: stop,
        target,
        source_signal_id: s.id,
      });
      setTakingId(null);
      setTakeMsg(`Tracking ${s.ticker} in Trades ✓`);
    } catch {
      setTakeMsg("Failed to record the trade.");
    } finally {
      setTaking(false);
    }
  };

  const load = () => {
    const f = filterRef.current;
    const url = f === "ALL" ? "/api/v1/signals?limit=100" : `/api/v1/signals?limit=100&signal=${f}`;
    api
      .get<SignalsResponse>(url)
      .then((res) => {
        setSignals(res.data.signals);
        setError(null);
      })
      .catch(() => setError("Failed to load signals."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setLoading(true);
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="bg-brand bg-clip-text text-2xl font-bold tracking-tight text-transparent">
            Signals
          </h1>
          <p className="mt-1 text-sm text-muted">
            Live alerts from the stock agent. Refreshes every minute.
          </p>
        </div>
        <div className="flex gap-1 rounded-full border border-line bg-surface p-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`tap rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                filter === f ? "bg-brand/10 text-content" : "text-muted hover:text-content"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-down">{error}</p>}
      {takeMsg && <p className="text-sm text-brand">{takeMsg}</p>}

      {loading ? (
        <p className="px-6 py-8 text-center text-sm text-faint">Loading…</p>
      ) : signals.length === 0 ? (
        <div className="card px-6 py-12 text-center">
          <p className="text-sm text-muted">
            No {filter === "ALL" ? "" : `${filter} `}signals yet.
          </p>
          <p className="mt-1 text-xs text-faint">
            The agent posts here when a setup clears all its gates.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {signals.map((s) => (
            <div key={s.id} className="card card-hover p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span
                    className={`rounded-md border px-2 py-1 text-xs font-bold ${signalClasses(s.signal)}`}
                  >
                    {signalLabel(s.signal)}
                  </span>
                  <div>
                    <p className="text-lg font-bold text-content">{s.ticker}</p>
                    <p className="text-xs text-faint">{fmtTime(s.created_at)}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="num text-lg font-bold text-content">${fmt(s.price)}</p>
                  <p className="text-xs text-muted">
                    {s.confidence}
                    {s.score != null && s.max_score != null
                      ? ` · ${s.score}/${s.max_score}`
                      : ""}
                    {s.regime ? ` · ${s.regime}` : ""}
                  </p>
                </div>
              </div>

              {(s.entry_price || s.target_price || s.stop_loss) && (
                <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-md bg-surface-2 py-2">
                    <p className="text-[10px] uppercase tracking-wide text-faint">Entry</p>
                    <p className="num text-sm font-semibold text-content">${fmt(s.entry_price)}</p>
                  </div>
                  <div className="rounded-md bg-surface-2 py-2">
                    <p className="text-[10px] uppercase tracking-wide text-faint">Target</p>
                    <p className="num text-sm font-semibold text-up">${fmt(s.target_price)}</p>
                  </div>
                  <div className="rounded-md bg-surface-2 py-2">
                    <p className="text-[10px] uppercase tracking-wide text-faint">Stop</p>
                    <p className="num text-sm font-semibold text-down">${fmt(s.stop_loss)}</p>
                  </div>
                </div>
              )}

              {(s.shares || s.risk_reward_ratio) && (
                <p className="mt-3 text-xs text-muted">
                  {s.shares ? `${fmt(s.shares)} shares` : ""}
                  {s.shares && s.risk_reward_ratio ? "  ·  " : ""}
                  {s.risk_reward_ratio ? `R:R ${fmt(s.risk_reward_ratio)}` : ""}
                </p>
              )}

              {s.exit_plan && (
                <div className="mt-3 rounded-md border border-brand/20 bg-brand/5 p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-brand">
                    Exit plan · stop / take-profit / trail
                  </p>
                  <p className="num mt-1 text-xs leading-relaxed text-content">{s.exit_plan}</p>
                </div>
              )}

              {s.reasoning && (
                <p className="mt-3 border-t border-line pt-3 text-xs leading-relaxed text-muted">
                  {s.reasoning}
                </p>
              )}

              {s.order_status && (
                <p className="mt-2 text-xs italic text-faint">{s.order_status}</p>
              )}

              {s.signal === "BUY" && (
                <div className="mt-4 border-t border-line pt-3">
                  {takingId === s.id ? (
                    <div className="flex flex-col gap-2">
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                        {(
                          [
                            ["shares", "Shares"],
                            ["entry", "Entry $"],
                            ["stop", "Stop $"],
                            ["target", "Target $"],
                          ] as const
                        ).map(([key, label]) => (
                          <div key={key}>
                            <label className="block text-[10px] uppercase tracking-wide text-faint">
                              {label}
                            </label>
                            <input
                              type="number"
                              step="0.0001"
                              value={form[key]}
                              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                              className="mt-0.5 w-full rounded-md border border-line bg-surface px-2 py-1 text-sm text-content focus:border-brand focus:outline-none"
                            />
                          </div>
                        ))}
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => submitTake(s)}
                          disabled={taking}
                          className="tap rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
                        >
                          {taking ? "Saving…" : "Confirm trade"}
                        </button>
                        <button
                          onClick={() => setTakingId(null)}
                          className="tap rounded-md border border-line px-3 py-1.5 text-xs font-medium text-muted hover:text-content"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => openTake(s)}
                      className="tap rounded-md border border-brand/40 px-3 py-1.5 text-xs font-medium text-brand hover:bg-brand/10"
                    >
                      I took this trade
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
