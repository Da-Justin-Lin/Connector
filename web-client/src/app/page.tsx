import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="animate-fade-in flex flex-col items-center text-center">
        <span className="mb-6 inline-flex items-center gap-2 rounded-full border border-line/70 bg-surface/60 px-4 py-1.5 text-xs font-medium text-muted backdrop-blur-sm">
          <span className="h-1.5 w-1.5 rounded-full bg-up" />
          All your accounts, one view
        </span>
        <h1 className="bg-brand bg-clip-text text-5xl font-bold tracking-tight text-transparent sm:text-6xl">
          Connector
        </h1>
        <p className="mt-4 max-w-md text-lg text-muted">
          Your unified investment portfolio, beautifully in one place.
        </p>
        <Link
          href="/dashboard"
          className="mt-8 rounded-full bg-brand px-7 py-3 font-semibold text-white shadow-lift transition-all hover:-translate-y-0.5 hover:opacity-90"
        >
          Go to Dashboard
        </Link>
      </div>
    </main>
  );
}
