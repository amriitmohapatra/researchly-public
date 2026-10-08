import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { LEARN_CARDS } from "@researchly/contract";
import { Lesson } from "@/components/pages/Lessons";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { cardById, groupedCards } from "@/lib/learn";

/** One page per Learn card, known at build time; any other id is a 404. */
export const dynamicParams = false;

export function generateStaticParams() {
  return LEARN_CARDS.map((c) => ({ id: c.id }));
}

type Params = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const card = cardById((await params).id);
  return card ? { title: `${card.title} | Researchly`, description: card.summary } : { title: "Lesson not found | Researchly" };
}

/** One lesson (S4c): the principle, Before and After, a habit for your own draft, and the source. Static. */
export default async function LessonPage({ params }: Params) {
  const card = cardById((await params).id);
  if (!card) notFound();
  // Previous and next in reading order (the index's order).
  const order = groupedCards().flatMap((g) => g.cards);
  const i = order.findIndex((c) => c.id === card.id);
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to the lesson
      </a>
      <SiteHeader />
      <main id="main" className="wrap" tabIndex={-1}>
        <Lesson card={card} prev={order[i - 1] ?? null} next={order[i + 1] ?? null} />
      </main>
      <SiteFooter />
    </>
  );
}
