"use client";

import { useEffect, useState } from "react";

import api from "@/services/api";

interface Holding {
  ticker: string | null;
  name: string | null;
  security_type: string | null;
  quantity: number;
  institution_price: number;
  market_value: number;
  cost_basis: number | null;
  account_name: string | null;
  account_type: string | null;
}

interface HoldingsData {
  holdings: Holding[];
  total_value: number;
  connected_accounts: number;
}

function fmt(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-1 text-3xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

export default function HoldingsSection() {
  const [data, setData] = useState<HoldingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<HoldingsData>("/api/v1/snaptrade/holdings")
      .then(({ data }) => setData(data))
      .catch(() => setError("Failed to load holdings."))
      .finally(() => setLoading(false));
  }, []);

  const totalValue = data ? `$${fmt(data.total_value)}` : "—";
  const connectedAccounts = data ? String(data.connected_accounts) : "—";

  return (
    <>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard label="Total Portfolio Value" value={loading ? "…" : totalValue} />
        <StatCard label="YTD Return" value="—" />
        <StatCard label="Connected Accounts" value={loading ? "…" : connectedAccounts} />
      </div>

      {error && <p className="mt-6 text-sm text-red-500">{error}</p>}

      {!loading && !error && data && data.holdings.length > 0 && (
        <div className="mt-8 overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {["Ticker", "Name", "Type", "Qty", "Price", "Market Value", "Cost Basis", "Account"].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.holdings.map((h, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{h.ticker ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-700">{h.name ?? "—"}</td>
                  <td className="px-4 py-3 capitalize text-gray-500">{h.security_type || "—"}</td>
                  <td className="px-4 py-3 text-gray-700">{h.quantity.toFixed(4)}</td>
                  <td className="px-4 py-3 text-gray-700">${h.institution_price.toFixed(2)}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">${fmt(h.market_value)}</td>
                  <td className="px-4 py-3 text-gray-700">
                    {h.cost_basis != null ? `$${fmt(h.cost_basis)}` : "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-500">{h.account_name ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && !error && data && data.holdings.length === 0 && data.connected_accounts === 0 && (
        <p className="mt-6 text-sm text-gray-500">
          Connect an account above to see your holdings.
        </p>
      )}

      {!loading && !error && data && data.holdings.length === 0 && data.connected_accounts > 0 && (
        <p className="mt-6 text-sm text-gray-500">No holdings found in your connected accounts.</p>
      )}
    </>
  );
}
