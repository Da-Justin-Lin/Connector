"use client";

import { useCallback, useEffect, useState } from "react";
import {
  PlaidLinkOnSuccess,
  usePlaidLink as usePlaidLinkBase,
} from "react-plaid-link";

import api from "@/services/api";

export function usePlaidLink() {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .post<{ link_token: string }>("/api/v1/plaid/link-token")
      .then(({ data }) => setLinkToken(data.link_token))
      .catch(() => setError("Could not initialize Plaid Link. Is the API server running?"));
  }, []);

  const onSuccess = useCallback<PlaidLinkOnSuccess>(async (publicToken) => {
    try {
      await api.post("/api/v1/plaid/exchange-token", { public_token: publicToken });
      window.location.reload();
    } catch {
      setError("Token exchange failed.");
    }
  }, []);

  const { open, ready } = usePlaidLinkBase({
    token: linkToken ?? "",
    onSuccess,
  });

  return { open, ready, error };
}
