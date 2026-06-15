import ConnectAccountButton from "@/components/ConnectAccountButton";
import HoldingsSection from "@/components/HoldingsSection";

export default function DashboardPage() {
  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Overview</h1>
        <ConnectAccountButton />
      </div>
      <HoldingsSection />
    </div>
  );
}
