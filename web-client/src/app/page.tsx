import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">Connector</h1>
        <p className="text-lg text-gray-600 mb-8">
          Your unified investment portfolio, in one place.
        </p>
        <Link
          href="/dashboard"
          className="rounded-lg bg-indigo-600 px-6 py-3 text-white font-semibold hover:bg-indigo-700 transition-colors"
        >
          Go to Dashboard
        </Link>
      </div>
    </main>
  );
}
