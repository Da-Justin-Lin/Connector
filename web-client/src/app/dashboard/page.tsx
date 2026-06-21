"use client";

import { useState } from "react";

import AccountFilter from "@/components/AccountFilter";
import AllocationBreakdown from "@/components/AllocationBreakdown";
import ConnectAccountButton from "@/components/ConnectAccountButton";
import HoldingsSection from "@/components/HoldingsSection";
import PortfolioTrend from "@/components/PortfolioTrend";

export default function DashboardPage() {
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-gray-900">Overview</h1>
        <div className="flex items-center gap-4">
          <AccountFilter value={selectedAccountId} onChange={setSelectedAccountId} />
          <ConnectAccountButton />
        </div>
      </div>
      <PortfolioTrend accountId={selectedAccountId} />
      <AllocationBreakdown accountId={selectedAccountId} />
      <HoldingsSection accountId={selectedAccountId} />
    </div>
  );
}
