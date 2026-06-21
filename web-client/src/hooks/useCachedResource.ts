import { useEffect, useRef, useState } from "react";

import api from "@/services/api";

// Per-namespace in-memory caches, keyed within a namespace by a caller key.
// Persist across navigation within the session so revisiting a view renders
// instantly while a fresh copy loads in the background.
const caches = new Map<string, Map<string, unknown>>();

function cacheFor(namespace: string): Map<string, unknown> {
  let c = caches.get(namespace);
  if (!c) {
    c = new Map();
    caches.set(namespace, c);
  }
  return c;
}

interface Options<T> {
  // When the server signals it is still refreshing in the background, pull a
  // fresh copy after a short delay (capped per key).
  isStale?: (data: T) => boolean;
}

interface Result<T> {
  data: T | null;
  loading: boolean; // true only on a cold cache (no data to show yet)
  revalidating: boolean; // a request is in flight while data is shown
  error: boolean;
}

export function useCachedResource<T>(
  namespace: string,
  key: string,
  url: string,
  options?: Options<T>,
): Result<T> {
  const cache = cacheFor(namespace);
  const [data, setData] = useState<T | null>(
    (cache.get(key) as T | undefined) ?? null,
  );
  const [loading, setLoading] = useState(!cache.has(key));
  const [revalidating, setRevalidating] = useState(false);
  const [error, setError] = useState(false);
  const [tick, setTick] = useState(0);
  const attempts = useRef<Map<string, number>>(new Map());
  const isStaleRef = useRef(options?.isStale);
  isStaleRef.current = options?.isStale;

  useEffect(() => {
    const cached = cache.get(key) as T | undefined;
    if (cached !== undefined) {
      setData(cached);
      setLoading(false);
    } else {
      setData(null);
      setLoading(true);
    }
    setRevalidating(true);
    setError(false);

    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    api
      .get<T>(url)
      .then(({ data }) => {
        cache.set(key, data);
        if (cancelled) return;
        setData(data);
        if (isStaleRef.current?.(data)) {
          const n = attempts.current.get(key) ?? 0;
          if (n < 3) {
            attempts.current.set(key, n + 1);
            retry = setTimeout(() => setTick((t) => t + 1), 3000);
          }
        } else {
          attempts.current.delete(key);
        }
      })
      .catch(() => {
        if (!cancelled && cached === undefined) setError(true);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setRevalidating(false);
        }
      });

    return () => {
      cancelled = true;
      if (retry) clearTimeout(retry);
    };
    // isStale is read via ref so it doesn't need to be a dependency.
  }, [cache, key, url, tick]);

  return { data, loading, revalidating, error };
}
