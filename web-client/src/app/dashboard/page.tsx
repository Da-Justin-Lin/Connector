import ConnectAccountButton from "@/components/ConnectAccountButton";
import HoldingsSection from "@/components/HoldingsSection";
import PortfolioTrend from "@/components/PortfolioTrend";

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Overview</h1>
        <ConnectAccountButton />
      </div>
      <PortfolioTrend />
      <HoldingsSection />
    </div>
  );
}
