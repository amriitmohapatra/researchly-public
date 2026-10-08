import { Checker } from "@/components/Checker";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { WhyResearchly } from "@/components/WhyResearchly";

/**
 * The checker: paste text (S1) or, signed in, check a file (S2).
 *
 * This server component renders only static chrome. All document text lives
 * in <Checker/>, a client component that sends it straight to the engine.
 */
export default function Home() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to the checker
      </a>
      <SiteHeader home />
      <main id="main" className="wrap" tabIndex={-1}>
        <div className="intro">
          <h1>Check a draft</h1>
          <p className="lede">
            Section-aware feedback on research writing. Each suggestion says what it noticed, why it matters and where
            the advice comes from. You make every change yourself.
          </p>
        </div>
        <Checker />
        <WhyResearchly />
      </main>
      <SiteFooter />
    </>
  );
}
