"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import { useRouter } from "next/navigation";

import AnimatedNumber from "@/components/AnimatedNumber";
import { useCachedResource } from "@/hooks/useCachedResource";
import api from "@/services/api";

interface Holding {
  ticker: string | null;
  name: string | null;
  security_type: string | null;
  quantity: number;
  institution_price: number;
  market_value: number;
  cost_basis: number | null;
}

interface AccountSection {
  snaptrade_account_id: string;
  institution_name: string | null;
  account_name: string | null;
  account_type: string | null;
  cash: number;
  holdings_value: number;
  total_value: number;
  holdings: Holding[];
}

interface HoldingsData {
  accounts: AccountSection[];
  total_value: number;
  total_cash: number;
  connected_accounts: number;
  stale?: boolean;
  last_synced_at?: string | null;
}

function fmt(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={`card card-hover p-6 ${accent ? "shadow-glow" : ""}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="num mt-1 text-3xl font-bold tracking-tight text-content">{value}</p>
    </div>
  );
}

function AccountCard({
  section,
  onSelectSymbol,
  onRemoved,
}: {
  section: AccountSection;
  onSelectSymbol: (ticker: string) => void;
  onRemoved: () => void;
}) {
  const title =
    section.institution_name || section.account_name || "Brokerage Account";
  const subtitle =
    section.account_name && section.institution_name ? section.account_name : null;
  const [removing, setRemoving] = useState(false);

  const handleRemove = async () => {
    const label = subtitle ? `${title} — ${subtitle}` : title;
    if (
      !window.confirm(
        `Permanently disconnect "${label}"?\n\n` +
          "This removes the brokerage connection from SnapTrade and deletes this " +
          "account's holdings, orders, and deposits. Other accounts on the same " +
          "connection may be disconnected too. This can't be undone.",
      )
    ) {
      return;
    }
    setRemoving(true);
    try {
      await api.delete(
        `/api/v1/snaptrade/accounts/${encodeURIComponent(section.snaptrade_account_id)}`,
      );
      onRemoved();
    } catch {
      window.alert("Couldn't disconnect that account. Please try again.");
      setRemoving(false);
    }
  };

  return (
    <div className="overflow-hidden card">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line bg-surface-2 px-6 py-4">
        <div>
          <p className="text-base font-semibold text-content">{title}</p>
          {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-6 text-right text-sm">
          <div>
            <p className="text-xs text-muted">Cash</p>
            <p className="num font-medium text-content">${fmt(section.cash)}</p>
          </div>
          <div>
            <p className="text-xs text-muted">Holdings</p>
            <p className="num font-medium text-content">${fmt(section.holdings_value)}</p>
          </div>
          <div>
            <p className="text-xs text-muted">Total</p>
            <p className="num font-semibold text-content">${fmt(section.total_value)}</p>
          </div>
          <button
            onClick={handleRemove}
            disabled={removing}
            title="Permanently disconnect this account"
            className="tap rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-muted transition-colors hover:border-down hover:text-down disabled:opacity-50"
          >
            {removing ? "Removing…" : "Remove"}
          </button>
        </div>
      </div>

      {section.holdings.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="bg-surface">
              <tr>
                {["Ticker", "Name", "Type", "Qty", "Price", "Market Value", "Cost Basis"].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {section.holdings.map((h, i) => {
                const clickable = !!h.ticker;
                return (
                  <tr
                    key={i}
                    className={`${
                      clickable
                        ? "cursor-pointer hover:bg-brand-soft"
                        : "hover:bg-surface-2"
                    }`}
                    onClick={() => clickable && onSelectSymbol(h.ticker!)}
                  >
                    <td className="px-4 py-3 font-medium text-content">
                      {clickable ? (
                        <span className="text-brand hover:underline">{h.ticker}</span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3 text-content">{h.name ?? "—"}</td>
                    <td className="px-4 py-3 capitalize text-muted">{h.security_type || "—"}</td>
                    <td className="num px-4 py-3 text-content">{h.quantity.toFixed(4)}</td>
                    <td className="num px-4 py-3 text-content">${h.institution_price.toFixed(2)}</td>
                    <td className="num px-4 py-3 font-medium text-content">${fmt(h.market_value)}</td>
                    <td className="num px-4 py-3 text-content">
                      {h.cost_basis != null ? `$${fmt(h.cost_basis)}` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="px-6 py-4 text-sm text-muted">
          No holdings in this account.
        </p>
      )}
    </div>
  );
}

interface HoldingsSectionProps {
  accountId?: string | null;
}

export default function HoldingsSection({ accountId = null }: HoldingsSectionProps) {
  const router = useRouter();
  const qs = accountId ? `?account_id=${accountId}` : "";
  const { data, loading, revalidating, error } = useCachedResource<HoldingsData>(
    "holdings",
    accountId ?? "ALL",
    `/api/v1/snaptrade/holdings${qs}`,
    { isStale: (d) => !!d.stale },
  );

  const connectedAccounts = data ? String(data.connected_accounts) : "—";
  const updating = (revalidating || data?.stale) && data;

  return (
    <>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label="Total Portfolio Value"
          accent
          value={
            loading || !data ? (
              "…"
            ) : (
              <AnimatedNumber value={data.total_value} prefix="$" sensitive />
            )
          }
        />
        <StatCard
          label="Total Cash"
          value={
            loading || !data ? (
              "…"
            ) : (
              <AnimatedNumber value={data.total_cash} prefix="$" sensitive />
            )
          }
        />
        <StatCard label="Connected Accounts" value={loading ? "…" : connectedAccounts} />
      </div>

      {updating && (
        <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-brand">
          <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
          Updating holdings…
        </p>
      )}

      {error && <p className="mt-6 text-sm text-down">Failed to load holdings.</p>}

      {!loading && !error && data && data.accounts.length > 0 && (
        <div className="mt-8 flex flex-col gap-6">
          {data.accounts.map((section) => (
            <AccountCard
              key={section.snaptrade_account_id}
              section={section}
              onSelectSymbol={(symbol) =>
                router.push(`/dashboard/positions/${encodeURIComponent(symbol)}`)
              }
              onRemoved={() => window.location.reload()}
            />
          ))}
        </div>
      )}

      {!loading && !error && data && data.accounts.length === 0 && (
        <p className="mt-6 text-sm text-muted">
          Connect an account above to see your holdings.
        </p>
      )}
    </>
  );
}
