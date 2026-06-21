import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { themeInitScript } from "@/components/ThemeToggle";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
// Tabular monospace for live financial figures so digits don't jitter on update.
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Connector — Investment Aggregator",
  description: "Unified view of all your investment accounts",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className={`${inter.variable} ${mono.variable} font-sans`}>{children}</body>
    </html>
  );
}
