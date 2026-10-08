import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Progress } from "@/components/pages/Progress";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { ACCOUNTS_ENABLED } from "@/lib/config";

export const metadata: Metadata = {
  title: "Your progress | Researchly",
};

/**
 * The personal progress view (S4c), signed in and opted in only. Static
 * chrome here; the counts are read in the browser by <Progress/>, straight
 * from Supabase. A build without accounts has no progress page.
 */
export default function ProgressPage() {
  if (!ACCOUNTS_ENABLED) notFound();
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to your progress
      </a>
      <SiteHeader />
      <main id="main" className="wrap" tabIndex={-1}>
        <p className="back-link">
          <Link href="/">Back to the checker</Link>
        </p>
        <div className="intro">
          <h1>Your progress</h1>
          <p className="lede">
            How often each check fired in your own drafts over time, if you chose to keep it. Counts only, never your
            text.
          </p>
        </div>
        <Progress />
      </main>
      <SiteFooter />
    </>
  );
}
