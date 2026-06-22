"use client";

import { useEffect, useRef, useState } from "react";

import {
  INDICATOR_COLORS,
  INDICATOR_MAP,
  INDICATORS,
  type Indicator,
} from "./indicators";

interface IndicatorControlsProps {
  indicators: Indicator[];
  onAdd: (type: string) => void;
  onRemove: (id: string) => void;
  onPeriodChange: (id: string, period: number) => void;
  onColorChange: (id: string, color: string) => void;
}

/**
 * Custom "add indicator" menu + active-indicator chips. Each chip exposes a
 * color swatch (per-MA color so overlapping averages stay distinguishable), an
 * editable period, and a remove button. Popovers close on outside click.
 */
export default function IndicatorControls({
  indicators,
  onAdd,
  onRemove,
  onPeriodChange,
  onColorChange,
}: IndicatorControlsProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [colorFor, setColorFor] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        setColorFor(null);
      }
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, []);

  return (
    <div ref={rootRef} className="flex flex-wrap items-center gap-2">
      <div className="relative">
        <button
          type="button"
          onClick={() => setMenuOpen((o) => !o)}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          className="tap flex items-center gap-1 rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-xs font-medium text-content transition-colors hover:bg-surface-3"
        >
          <span className="text-brand">＋</span> Indicator
        </button>
        {menuOpen && (
          <div
            role="menu"
            className="absolute left-0 top-full z-20 mt-1 min-w-[12rem] overflow-hidden rounded-lg border border-line bg-surface p-1 shadow-lift"
          >
            {INDICATORS.map((d) => (
              <button
                key={d.type}
                type="button"
                role="menuitem"
                onClick={() => {
                  onAdd(d.type);
                  setMenuOpen(false);
                }}
                className="tap block w-full rounded-md px-2.5 py-1.5 text-left text-xs text-content transition-colors hover:bg-surface-2"
              >
                {d.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {indicators.map((ind) => (
        <div
          key={ind.id}
          className="relative flex items-center gap-1.5 rounded-lg border border-line bg-surface-2 py-1 pl-1.5 pr-1 text-xs"
        >
          <button
            type="button"
            aria-label="Change color"
            onClick={() => setColorFor((cur) => (cur === ind.id ? null : ind.id))}
            className="tap h-3.5 w-3.5 rounded-full ring-1 ring-inset ring-black/20 transition-transform hover:scale-110"
            style={{ backgroundColor: ind.color }}
          />
          {colorFor === ind.id && (
            <div className="absolute left-0 top-full z-20 mt-1 grid grid-cols-3 gap-1.5 rounded-lg border border-line bg-surface p-2 shadow-lift">
              {INDICATOR_COLORS.map((col) => (
                <button
                  key={col}
                  type="button"
                  aria-label={`Color ${col}`}
                  onClick={() => {
                    onColorChange(ind.id, col);
                    setColorFor(null);
                  }}
                  className={`tap h-4 w-4 rounded-full transition-transform hover:scale-110 ${
                    col === ind.color ? "ring-2 ring-content ring-offset-1 ring-offset-surface" : ""
                  }`}
                  style={{ backgroundColor: col }}
                />
              ))}
            </div>
          )}

          <span className="font-semibold text-content">{INDICATOR_MAP[ind.type]?.short ?? ind.type}</span>
          <input
            type="number"
            min={1}
            value={ind.period}
            onChange={(e) => {
              const p = Number.parseInt(e.target.value, 10);
              if (Number.isFinite(p) && p > 0) onPeriodChange(ind.id, p);
            }}
            className="num w-11 rounded border border-line bg-surface px-1 py-0.5 text-right text-content focus:outline-none focus:ring-1 focus:ring-brand"
          />
          <button
            type="button"
            aria-label="Remove indicator"
            onClick={() => onRemove(ind.id)}
            className="tap flex h-5 w-5 items-center justify-center rounded text-faint transition-colors hover:bg-surface hover:text-down"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
