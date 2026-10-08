import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Settings } from "@/components/Settings";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { ACCOUNTS_ENABLED } from "@/lib/config";

export const metadata: Metadata = {
  title: "Settings and dictionary | Researchly",
};

/**
 * Account settings (S2). Static chrome here; everything about the account is
 * read and written in the browser by <Settings/> (a client component), straight
 * to Supabase. A build without accounts has no settings page at all.
 */
export default function SettingsPage() {
  if (!ACCOUNTS_ENABLED) notFound();
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to your settings
      </a>
      <SiteHeader />
      <main id="main" className="wrap" tabIndex={-1}>
        <p className="back-link">
          <Link href="/">Back to the checker</Link>
        </p>
        <div className="intro">
          <h1>Settings and dictionary</h1>
          <p className="lede">
            These follow you to every device you sign in on. They hold rule names, words and switches, never any of
            your text.
          </p>
        </div>
        <Settings />
      </main>
      <SiteFooter />
    </>
  );
}
