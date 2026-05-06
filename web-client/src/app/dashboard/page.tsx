import HoldingsSection from "@/components/HoldingsSection";
import PlaidLinkButton from "@/components/PlaidLinkButton";

export default function DashboardPage() {
  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Overview</h1>
        <PlaidLinkButton />
      </div>
      <HoldingsSection />
    </div>
  );
}
