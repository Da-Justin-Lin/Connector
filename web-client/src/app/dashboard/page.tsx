"use client";

import { useState } from "react";

import AccountFilter from "@/components/AccountFilter";
import AllocationBreakdown from "@/components/AllocationBreakdown";
import ConnectAccountButton from "@/components/ConnectAccountButton";
import HoldingsSection from "@/components/HoldingsSection";
import PortfolioTrend from "@/components/PortfolioTrend";
import PageHeader from "@/components/ui/PageHeader";

export default function DashboardPage() {
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Overview"
        subtitle="Your portfolio across every connected account."
        actions={
          <>
            <AccountFilter value={selectedAccountId} onChange={setSelectedAccountId} />
            <ConnectAccountButton />
          </>
        }
      />
      <PortfolioTrend accountId={selectedAccountId} />
      <AllocationBreakdown accountId={selectedAccountId} />
      <HoldingsSection accountId={selectedAccountId} />
    </div>
  );
}
