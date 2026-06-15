"use client";

import { useCallback, useState } from "react";

import api from "@/services/api";

export function useSnapTradeConnect() {
  const [loginLink, setLoginLink] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const open = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const { data } = await api.post<{ redirect_uri: string }>(
        "/api/v1/snaptrade/connection-url",
      );
      setLoginLink(data.redirect_uri);
      setIsOpen(true);
    } catch {
      setError("Could not start SnapTrade connection. Is the API server running?");
    } finally {
      setLoading(false);
    }
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    setLoginLink(null);
  }, []);

  const onSuccess = useCallback(async () => {
    try {
      await api.post("/api/v1/snaptrade/sync-accounts");
      window.location.reload();
    } catch {
      setError("Failed to sync accounts after connection.");
    } finally {
      close();
    }
  }, [close]);

  const onError = useCallback((err: { errorCode?: string; statusCode?: string; description?: string }) => {
    setError(err?.description || "Connection failed.");
    close();
  }, [close]);

  return { open, close, isOpen, loginLink, loading, error, onSuccess, onError };
}
