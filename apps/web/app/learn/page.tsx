import type { Metadata } from "next";
import Link from "next/link";
import { LessonIndex } from "@/components/pages/Lessons";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { groupedCards } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Lessons | Researchly",
  description: "Short lessons behind Researchly's suggestions: the principle, a before and after, and a habit to try on your own draft.",
};

/** Every Learn card (S4c), grouped in the engine's order. Static: no engine call, no text. */
export default function LearnPage() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to the lessons
      </a>
      <SiteHeader />
      <main id="main" className="wrap" tabIndex={-1}>
        <p className="back-link">
          <Link href="/">Back to the checker</Link>
        </p>
        <div className="intro">
          <h1>Lessons</h1>
          <p className="lede">
            The ideas behind the suggestions, one at a time: what the principle is, a passage before and after, and a
            habit to try on your own draft.
          </p>
        </div>
        <LessonIndex groups={groupedCards()} />
      </main>
      <SiteFooter />
    </>
  );
}
