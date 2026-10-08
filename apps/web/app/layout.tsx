import type { Metadata, Viewport } from "next";
import { connection } from "next/server";
import "./globals.css";

export const metadata: Metadata = {
  title: "Researchly: a writing coach for research",
  description:
    "Explainable, section-aware feedback on research writing. It advises; it never drafts. Your text is analysed in memory and never stored.",
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f5f3" },
    { media: "(prefers-color-scheme: dark)", color: "#14161a" },
  ],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Every route renders per request so proxy.ts can attach a fresh CSP nonce
  // to Next.js's inline bootstrap scripts (a static page would have none).
  await connection();
  return (
    <html lang="en-GB">
      <body>{children}</body>
    </html>
  );
}
