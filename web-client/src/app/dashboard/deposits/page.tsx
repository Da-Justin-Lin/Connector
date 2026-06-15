"use client";

import { useEffect, useState } from "react";

import api from "@/services/api";

interface Deposit {
  id: string;
  amount: number;
  deposited_at: string;
  note: string | null;
  created_at: string;
}

interface DepositsResponse {
  deposits: Deposit[];
  total_principal: number;
}

function fmt(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default function DepositsPage() {
  const [data, setData] = useState<DepositsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [amount, setAmount] = useState("");
  const [depositedAt, setDepositedAt] = useState(() => new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .get<DepositsResponse>("/api/v1/deposits")
      .then(({ data }) => setData(data))
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
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/api/v1/deposits", {
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

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-gray-900">Deposits</h1>
        {data && (
          <div className="rounded-xl border border-gray-200 bg-white px-6 py-3 shadow-sm">
            <p className="text-xs text-gray-500">Total Principal</p>
            <p className="text-2xl font-bold text-gray-900">${fmt(data.total_principal)}</p>
          </div>
        )}
      </div>

      <form
        onSubmit={submit}
        className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
      >
        <p className="mb-4 text-sm font-medium text-gray-700">Add a deposit</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          <div>
            <label className="block text-xs font-medium text-gray-500">Amount ($)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500">Date</label>
            <input
              type="date"
              value={depositedAt}
              onChange={(e) => setDepositedAt(e.target.value)}
              required
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-gray-500">Note (optional)</label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. ACH from Chase"
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="mt-4 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {submitting ? "Adding…" : "Add deposit"}
        </button>
      </form>

      {error && <p className="text-sm text-rose-500">{error}</p>}

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {loading ? (
          <p className="px-6 py-8 text-center text-sm text-gray-400">Loading…</p>
        ) : !data || data.deposits.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-gray-500">
            No deposits yet. Add your starting principal above.
          </p>
        ) : (
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {["Date", "Amount", "Note", ""].map((h) => (
                  <th
                    key={h}
                    className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.deposits.map((d) => (
                <tr key={d.id} className="hover:bg-gray-50">
                  <td className="px-6 py-3 text-gray-700">{fmtDate(d.deposited_at)}</td>
                  <td className="px-6 py-3 font-medium text-gray-900">${fmt(d.amount)}</td>
                  <td className="px-6 py-3 text-gray-500">{d.note ?? "—"}</td>
                  <td className="px-6 py-3 text-right">
                    <button
                      onClick={() => remove(d.id)}
                      className="text-xs font-medium text-rose-600 hover:text-rose-800"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
