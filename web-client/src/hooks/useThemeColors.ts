"use client";

import { useEffect, useState } from "react";

export interface ThemeColors {
  brand: string;
  brand2: string;
  up: string;
  down: string;
  muted: string;
  faint: string;
  line: string;
}

const FALLBACK: ThemeColors = {
  brand: "rgb(79 70 229)",
  brand2: "rgb(124 58 237)",
  up: "rgb(16 185 129)",
  down: "rgb(239 68 68)",
  muted: "rgb(107 114 128)",
  faint: "rgb(156 163 175)",
  line: "rgb(229 231 235)",
};

function read(): ThemeColors {
  if (typeof window === "undefined") return FALLBACK;
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string) => {
    const raw = cs.getPropertyValue(name).trim();
    return raw ? `rgb(${raw})` : "";
  };
  return {
    brand: v("--brand") || FALLBACK.brand,
    brand2: v("--brand-2") || FALLBACK.brand2,
    up: v("--up") || FALLBACK.up,
    down: v("--down") || FALLBACK.down,
    muted: v("--muted") || FALLBACK.muted,
    faint: v("--faint") || FALLBACK.faint,
    line: v("--line") || FALLBACK.line,
  };
}

/**
 * Resolves the current theme's semantic colors to concrete `rgb(...)` strings
 * for libraries (recharts) that can't consume CSS custom properties directly.
 * Re-reads whenever the `dark` class on <html> changes.
 */
export function useThemeColors(): ThemeColors {
  const [colors, setColors] = useState<ThemeColors>(FALLBACK);

  useEffect(() => {
    setColors(read());
    const observer = new MutationObserver(() => setColors(read()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  return colors;
}
