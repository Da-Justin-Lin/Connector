"use client";

import { useSyncExternalStore } from "react";

/**
 * Tiny global store for the "hide balances" privacy toggle. Lives outside React
 * so any money-displaying component can read it without a provider, and the eye
 * button can live anywhere. Persists the choice to localStorage.
 */

const KEY = "hideBalances";
let hidden = false;
const listeners = new Set<() => void>();

if (typeof window !== "undefined") {
  try {
    hidden = localStorage.getItem(KEY) === "1";
  } catch {
    /* ignore */
  }
}

function emit() {
  listeners.forEach((l) => l());
}

export function togglePrivacy() {
  hidden = !hidden;
  try {
    localStorage.setItem(KEY, hidden ? "1" : "0");
  } catch {
    /* ignore */
  }
  emit();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Returns whether balances are currently hidden. */
export function usePrivacy(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => hidden,
    () => false,
  );
}
