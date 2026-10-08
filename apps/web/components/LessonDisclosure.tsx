"use client";

import { learnCard, LEARN_PATH } from "@/lib/learn";

interface Props {
  /** The engine's `learn_ref`: a Learn card's id. Nothing renders without a known card. */
  learnRef: string | null | undefined;
}

/**
 * "The lesson": a quiet native disclosure, closed, that opens the Learn
 * card behind a suggestion, a missing move or a missing link in place:
 * its title, the lesson in everyday words, an invented before-and-after
 * pair quoted in the serif, a habit to check your own draft, and the
 * source set like a card's. "All lessons" opens the Learn page in a new
 * tab, so the results are never left behind. The card ships with the
 * page; opening it sends nothing.
 */
export function LessonDisclosure({ learnRef }: Props) {
  const card = learnCard(learnRef);
  if (!card) return null;
  return (
    <details className="lesson" data-testid="lesson" data-lesson={card.id}>
      <summary>The lesson</summary>
      <div className="lesson-body">
        <p className="lesson-title">{card.title}</p>
        <p className="lesson-text">{card.lesson}</p>
        <div className="lesson-pair">
          <figure className="lesson-example">
            <figcaption className="lesson-example-label">Before</figcaption>
            <blockquote className="lesson-quote">
              <q>{card.before}</q>
            </blockquote>
          </figure>
          <figure className="lesson-example">
            <figcaption className="lesson-example-label">After</figcaption>
            <blockquote className="lesson-quote">
              <q>{card.after}</q>
            </blockquote>
          </figure>
        </div>
        {card.habit.trim() ? (
          <p className="lesson-habit">
            <span className="lesson-habit-label">A habit to keep:</span> {card.habit}
          </p>
        ) : null}
        <p className="lesson-source">
          <span className="card-source-label">Source:</span> <cite>{card.source}</cite>
        </p>
        <p className="lesson-more">
          <a href={LEARN_PATH} target="_blank" rel="noopener" className="inline-link" data-testid="all-lessons">
            All lessons
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        </p>
      </div>
    </details>
  );
}
