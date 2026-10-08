import Link from "next/link";
import type { LearnCard } from "@researchly/contract";
import { lessonHref } from "@/lib/learn";

/**
 * The Learn pages (S4c), as server components: static text from the
 * contract's LEARN_CARDS, no engine call and no client script. The writing
 * shown (Before, After) is set in the serif, as the writer's own words are
 * everywhere else; the coach (titles, the lesson, the habit) in the sans.
 */

export function LessonIndex({ groups }: { groups: { group: string; cards: LearnCard[] }[] }) {
  return (
    <div className="lessons" data-testid="lesson-index">
      {groups.map(({ group, cards }) => {
        const id = `lessons-${group.toLowerCase().replace(/[^a-z]+/g, "-")}`;
        return (
          <section key={group} className="lesson-group" aria-labelledby={id} data-testid="lesson-group">
            <h2 id={id} className="lesson-group-title">
              {group}
            </h2>
            <ul className="lesson-list">
              {cards.map((c) => (
                <li key={c.id} className="lesson-item" data-testid="lesson-item">
                  <Link href={lessonHref(c)} className="lesson-link">
                    {c.title}
                  </Link>
                  <p className="lesson-summary">{c.summary}</p>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

export function Lesson({ card, prev, next }: { card: LearnCard; prev: LearnCard | null; next: LearnCard | null }) {
  return (
    <article className="lesson" aria-labelledby="lesson-title" data-testid="lesson">
      <p className="lesson-kicker muted">{card.group}</p>
      <h1 id="lesson-title" className="lesson-title">
        {card.title}
      </h1>
      <p className="lesson-text" data-testid="lesson-text">
        {card.lesson}
      </p>

      <div className="lesson-examples">
        <figure className="lesson-example lesson-before" data-testid="lesson-before">
          <figcaption className="lesson-example-label">Before</figcaption>
          <blockquote className="lesson-quote">
            <p>{card.before}</p>
          </blockquote>
        </figure>
        <figure className="lesson-example lesson-after" data-testid="lesson-after">
          <figcaption className="lesson-example-label">After</figcaption>
          <blockquote className="lesson-quote">
            <p>{card.after}</p>
          </blockquote>
        </figure>
      </div>

      <section className="lesson-habit" aria-labelledby="lesson-habit-title" data-testid="lesson-habit">
        <h2 id="lesson-habit-title" className="lesson-habit-title">
          Check your own draft
        </h2>
        <p>{card.habit}</p>
      </section>

      <p className="card-source lesson-source" data-testid="lesson-source">
        <span className="card-source-label">Source:</span> <cite>{card.source}</cite>
      </p>

      <nav className="lesson-nav" aria-label="More lessons">
        <p className="back-link">
          <Link href="/learn">All lessons</Link>
        </p>
        <ul className="lesson-nav-list">
          {prev ? (
            <li>
              <span className="muted">Previous: </span>
              <Link className="inline-link" href={lessonHref(prev)}>
                {prev.title}
              </Link>
            </li>
          ) : null}
          {next ? (
            <li>
              <span className="muted">Next: </span>
              <Link className="inline-link" href={lessonHref(next)}>
                {next.title}
              </Link>
            </li>
          ) : null}
        </ul>
      </nav>
    </article>
  );
}
