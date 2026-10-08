import type { Metadata } from "next";
import { OFFICE_JS_URL } from "@/lib/security";

export const metadata: Metadata = {
  title: "Researchly for Word",
  description: "Researchly's Word add-in: explained, section-aware suggestions in a sidebar. It advises; it never drafts.",
};

/**
 * The Word add-in's taskpane (S3). Microsoft requires add-ins to load
 * office.js from its own CDN with a plain script tag, before the page runs.
 * The three scripts run in order, before Next.js hydrates: office-guard.js
 * keeps history.pushState/replaceState, office.js may remove them, and
 * office-restore.js puts them back (Next.js's router needs them).
 * proxy.ts gives this route its own CSP: script-src allows exactly
 * Microsoft's office.js origin, and frame-ancestors the Office web origins.
 */
export default function WordLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {/* eslint-disable @next/next/no-sync-scripts -- order matters: office.js must load before the page runs (see above) */}
      <script src="/word/office-guard.js" />
      <script src={OFFICE_JS_URL} />
      <script src="/word/office-restore.js" />
      {/* eslint-enable @next/next/no-sync-scripts */}
      {children}
    </>
  );
}
