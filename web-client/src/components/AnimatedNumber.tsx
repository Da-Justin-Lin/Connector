"use client";

import { useEffect, useRef, useState } from "react";

import { usePrivacy } from "@/hooks/usePrivacy";

interface AnimatedNumberProps {
  value: number;
  /** Leading string, e.g. "$" or "+$". */
  prefix?: string;
  /** Trailing string, e.g. "%". */
  suffix?: string;
  decimals?: number;
  className?: string;
  /** Hide behind the privacy blur when balances are hidden. Default false. */
  sensitive?: boolean;
  /** Animate the roll-up. Default true. */
  animate?: boolean;
}

function format(n: number, decimals: number) {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Tabular-mono number that rolls/scrolls to its target value when it changes,
 * so switching views (1D → All-Time) feels alive instead of a hard flash.
 */
export default function AnimatedNumber({
  value,
  prefix = "",
  suffix = "",
  decimals = 2,
  className = "",
  sensitive = false,
  animate = true,
}: AnimatedNumberProps) {
  const hidden = usePrivacy();
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!animate) {
      setDisplay(value);
      return;
    }
    const from = fromRef.current;
    const to = value;
    if (from === to) return;
    const duration = 600;
    const start = performance.now();

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      // easeOutCubic for a snappy settle.
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (to - from) * eased);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      fromRef.current = value;
    };
  }, [value, animate]);

  return (
    <span className={`num ${sensitive && hidden ? "private" : ""} ${className}`}>
      {prefix}
      {format(display, decimals)}
      {suffix}
    </span>
  );
}
