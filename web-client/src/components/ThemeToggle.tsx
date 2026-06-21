"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

// Inline script (stringified) that runs before paint to set the theme class,
// avoiding a flash of the wrong theme. Mounted in <head> by the root layout.
export const themeInitScript = `(() => {
  try {
    const stored = localStorage.getItem("theme");
    const dark = stored ? stored === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
  } catch (_) {}
})();`;

function getInitial(): Theme {
  if (typeof document !== "undefined" && document.documentElement.classList.contains("dark")) {
    return "dark";
  }
  return "light";
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setTheme(getInitial());
    setMounted(true);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* ignore */
    }
  };

  // Avoid hydration mismatch — render a neutral placeholder until mounted.
  const isDark = mounted && theme === "dark";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle dark mode"
      className="relative grid h-9 w-9 place-items-center rounded-full border border-line/70 bg-surface/60 text-muted transition-colors hover:text-content hover:border-line"
    >
      <SunIcon className={`h-4 w-4 transition-all duration-300 ${isDark ? "scale-0 opacity-0" : "scale-100 opacity-100"}`} />
      <MoonIcon className={`absolute h-4 w-4 transition-all duration-300 ${isDark ? "scale-100 opacity-100" : "scale-0 opacity-0"}`} />
    </button>
  );
}

function SunIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  );
}

function MoonIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}
