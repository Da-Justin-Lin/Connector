"use client";

import { useEffect, useState } from "react";

import api from "@/services/api";

interface Deposit {
  id: string;
  investment_account_id: string;
  amount: number;
  deposited_at: string;
  note: string | null;
  created_at: string;
}

interface AccountPrincipal {
  investment_account_id: string;
  snaptrade_account_id: string;
  institution_name: string | null;
  account_name: string | null;
  total_principal: number;
}

interface DepositsResponse {
  deposits: Deposit[];
  total_principal: number;
  per_account: AccountPrincipal[];
}

interface AccountSection {
  snaptrade_account_id: string;
  institution_name: string | null;
  account_name: string | null;
}

interface HoldingsResponse {
  accounts: AccountSection[];
}

interface InvestmentAccount {
  id: string;
  snaptrade_account_id: string;
  institution_name: string | null;
  account_name: string | null;
}

function fmt(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function accountLabel(a: { institution_name: string | null; account_name: string | null }) {
  return a.institution_name || a.account_name || "Brokerage Account";
}

export default function DepositsPage() {
  const [data, setData] = useState<DepositsResponse | null>(null);
  const [accounts, setAccounts] = useState<InvestmentAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [accountId, setAccountId] = useState<string>("");
  const [amount, setAmount] = useState("");
  const [depositedAt, setDepositedAt] = useState(() => new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([
      api.get<DepositsResponse>("/api/v1/deposits"),
      // Use the user's account-list endpoint embedded in holdings; we just need
      // the institution+account_name+UUID, but the holdings endpoint doesn't
      // expose UUIDs. Use the dedicated /users/me/accounts shape instead.
      api.get<InvestmentAccount[]>("/api/v1/users/me/accounts"),
    ])
      .then(([depRes, accRes]) => {
        setData(depRes.data);
        setAccounts(accRes.data);
        if (!accountId && accRes.data.length > 0) {
          setAccountId(accRes.data[0].id);
        }
      })
      .catch(() => setError("Failed to load deposits."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const amt = Number(amount);
    if (!amt || amt <= 0) {
      setError("Amount must be greater than zero.");
      return;
    }
    if (!accountId) {
      setError("Pick an account.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/api/v1/deposits", {
        investment_account_id: accountId,
        amount: amt,
        deposited_at: new Date(depositedAt).toISOString(),
        note: note || null,
      });
      setAmount("");
      setNote("");
      setDepositedAt(new Date().toISOString().slice(0, 10));
      load();
    } catch {
      setError("Failed to add deposit.");
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this deposit?")) return;
    try {
      await api.delete(`/api/v1/deposits/${id}`);
      load();
    } catch {
      setError("Failed to delete deposit.");
    }
  };

  const accountLookup = new Map(accounts.map((a) => [a.id, a]));

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-content">Deposits</h1>
        {data && (
          <div className="card px-6 py-3">
            <p className="text-xs text-muted">Total Principal</p>
            <p className="text-2xl font-bold text-content">${fmt(data.total_principal)}</p>
          </div>
        )}
      </div>

      {data && data.per_account.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.per_account.map((pa) => (
            <div
              key={pa.investment_account_id}
              className="card p-4"
            >
              <p className="text-xs text-muted">{accountLabel(pa)}</p>
              <p className="mt-1 text-xl font-bold text-content">
                ${fmt(pa.total_principal)}
              </p>
              {pa.account_name && pa.institution_name && (
                <p className="text-xs text-faint">{pa.account_name}</p>
              )}
            </div>
          ))}
        </div>
      )}

      <form
        onSubmit={submit}
        className="card p-6"
      >
        <p className="mb-4 text-sm font-medium text-content">Add a deposit</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-5">
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-muted">Account</label>
            <select
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              required
              className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm focus:border-brand focus:outline-none"
            >
              {accounts.length === 0 && (
                <option value="">No connected accounts</option>
              )}
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {accountLabel(a)}
                  {a.account_name && a.institution_name ? ` — ${a.account_name}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-muted">Amount ($)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
              className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm focus:border-brand focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted">Date</label>
            <input
              type="date"
              value={depositedAt}
              onChange={(e) => setDepositedAt(e.target.value)}
              required
              className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm focus:border-brand focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted">Note</label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="optional"
              className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm focus:border-brand focus:outline-none"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={submitting || accounts.length === 0}
          className="mt-4 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {submitting ? "Adding…" : "Add deposit"}
        </button>
      </form>

      {error && <p className="text-sm text-down">{error}</p>}

      <div className="overflow-hidden card">
        {loading ? (
          <p className="px-6 py-8 text-center text-sm text-faint">Loading…</p>
        ) : !data || data.deposits.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-muted">
            No deposits yet. Add your starting principal above.
          </p>
        ) : (
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="bg-surface-2">
              <tr>
                {["Date", "Account", "Amount", "Note", ""].map((h) => (
                  <th
                    key={h}
                    className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.deposits.map((d) => {
                const acc = accountLookup.get(d.investment_account_id);
                return (
                  <tr key={d.id} className="hover:bg-surface-2">
                    <td className="px-6 py-3 text-content">{fmtDate(d.deposited_at)}</td>
                    <td className="px-6 py-3 text-content">
                      {acc ? accountLabel(acc) : "—"}
                    </td>
                    <td className="px-6 py-3 font-medium text-content">${fmt(d.amount)}</td>
                    <td className="px-6 py-3 text-muted">{d.note ?? "—"}</td>
                    <td className="px-6 py-3 text-right">
                      <button
                        onClick={() => remove(d.id)}
                        className="text-xs font-medium text-down hover:text-down hover:opacity-80"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
