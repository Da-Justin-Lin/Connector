import type { Config } from "tailwindcss";

const withAlpha = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        canvas: withAlpha("--canvas"),
        surface: withAlpha("--surface"),
        "surface-2": withAlpha("--surface-2"),
        "surface-3": withAlpha("--surface-3"),
        content: withAlpha("--content"),
        muted: withAlpha("--muted"),
        faint: withAlpha("--faint"),
        line: withAlpha("--line"),
        glass: withAlpha("--glass-border"),
        brand: {
          DEFAULT: withAlpha("--brand"),
          2: withAlpha("--brand-2"),
          soft: withAlpha("--brand-soft"),
        },
        up: withAlpha("--up"),
        down: withAlpha("--down"),
      },
      boxShadow: {
        soft: "var(--shadow-soft)",
        lift: "var(--shadow-lift)",
        glow: "var(--shadow-glow)",
      },
      backgroundImage: {
        brand: "linear-gradient(135deg, rgb(var(--brand)), rgb(var(--brand-2)))",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "pulse-glow": {
          "0%, 100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.4s cubic-bezier(0.22, 1, 0.36, 1) both",
        shimmer: "shimmer 1.5s infinite",
        "pulse-glow": "pulse-glow 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
