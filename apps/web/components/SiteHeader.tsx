import Link from "next/link";
import { ACCOUNTS_ENABLED, reportProblemHref } from "@/lib/config";
import { AccountMenu } from "./AccountMenu";

function BrandMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="brand-mark">
      <path d="M5 4.5h9.5a4.5 4.5 0 010 9H9.5L15 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 4.5V20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Static chrome shared by every page. The account control is a client
 * island that exists only in a build with accounts (S2); without them the
 * header is exactly the S1 header.
 */
export function SiteHeader({ home = false }: { home?: boolean }) {
  return (
    <header className="site-header">
      <div className={`wrap header-inner${ACCOUNTS_ENABLED ? " header-has-account" : ""}`}>
        {home ? (
          <p className="brand" translate="no">
            <BrandMark />
            Researchly
          </p>
        ) : (
          <Link href="/" className="brand brand-link" translate="no">
            <BrandMark />
            Researchly
          </Link>
        )}
        <p className="tagline">The writing coach you&rsquo;re allowed to use. It advises; it never drafts.</p>
        <div className="header-end">
          <nav className="site-nav" aria-label="Site">
            <Link href="/learn" className="site-nav-link" data-testid="nav-lessons">
              Lessons
            </Link>
          </nav>
          {ACCOUNTS_ENABLED ? (
            <div className="header-account">
              <AccountMenu />
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="wrap">
        <p>
          Researchly is confidential by design: text is processed in memory for the length of one request, then
          dropped. It is never logged, stored or used for training.
        </p>
        <p className="footer-report">
          Something wrong?{" "}
          <a className="inline-link" href={reportProblemHref("Researchly website: a problem")} data-testid="report-problem">
            Report a problem
          </a>{" "}
          by email. Please describe what happened; don&rsquo;t paste text from your draft.
        </p>
      </div>
    </footer>
  );
}
