import type { Metadata } from "next";
import Link from "next/link";
import { LabelStudio } from "@/components/pages/LabelStudio";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "Label flags | Researchly",
};

/**
 * The labelling tool for the S4 exit check (docs/labelling-guide.md), signed
 * in or not. Static chrome here; the paragraph goes from the browser straight
 * to the engine, like any check, and is never stored. Only the verdicts are
 * kept, in this browser, until they are exported.
 */
export default function LabelPage() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to labelling
      </a>
      <SiteHeader />
      <main id="main" className="wrap" tabIndex={-1}>
        <p className="back-link">
          <Link href="/">Back to the checker</Link>
        </p>
        <div className="intro">
          <h1>Label flags</h1>
          <p className="lede">
            Measure how often Researchly&rsquo;s flags are right on your own writing: check a paragraph, mark each flag
            Useful, Wrong or Unsure, and export the verdicts.
          </p>
        </div>
        <LabelStudio />
      </main>
      <SiteFooter />
    </>
  );
}
