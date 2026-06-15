"use client";

import { useEffect, useState } from "react";

import api from "@/services/api";

export interface AccountOption {
  snaptrade_account_id: string;
  institution_name: string | null;
  account_name: string | null;
}

interface HoldingsData {
  accounts: Array<{
    snaptrade_account_id: string;
    institution_name: string | null;
    account_name: string | null;
  }>;
}

interface AccountFilterProps {
  value: string | null;
  onChange: (accountId: string | null) => void;
}

function labelFor(opt: AccountOption) {
  if (opt.institution_name && opt.account_name) {
    return `${opt.institution_name} — ${opt.account_name}`;
  }
  return opt.institution_name || opt.account_name || opt.snaptrade_account_id.slice(0, 8);
}

export default function AccountFilter({ value, onChange }: AccountFilterProps) {
  const [options, setOptions] = useState<AccountOption[]>([]);

  useEffect(() => {
    api
      .get<HoldingsData>("/api/v1/snaptrade/holdings")
      .then(({ data }) =>
        setOptions(
          data.accounts.map((a) => ({
            snaptrade_account_id: a.snaptrade_account_id,
            institution_name: a.institution_name,
            account_name: a.account_name,
          })),
        ),
      )
      .catch(() => setOptions([]));
  }, []);

  if (options.length === 0) return null;

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="account-filter" className="text-sm font-medium text-gray-600">
        Account
      </label>
      <select
        id="account-filter"
        value={value ?? "ALL"}
        onChange={(e) => onChange(e.target.value === "ALL" ? null : e.target.value)}
        className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
      >
        <option value="ALL">All Accounts</option>
        {options.map((opt) => (
          <option key={opt.snaptrade_account_id} value={opt.snaptrade_account_id}>
            {labelFor(opt)}
          </option>
        ))}
      </select>
    </div>
  );
}
