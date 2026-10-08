import type { Category } from "@researchly/contract";
import { categoryMeta } from "@/lib/categories";

/** Shape differs per category so colour is never the only cue. Decorative: the label carries the meaning. */
export function CategoryIcon({ category }: { category: Category }) {
  const common = {
    width: 14,
    height: 14,
    viewBox: "0 0 16 16",
    "aria-hidden": true,
    focusable: false,
    className: "cat-icon",
  } as const;
  switch (category) {
    case "correction":
      // circle with a cross
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    case "improvement":
      // upward arrow
      return (
        <svg {...common}>
          <path d="M8 13V3.5M4 7.5L8 3.5l4 4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "convention":
      // open book
      return (
        <svg {...common}>
          <path
            d="M8 4.5C6.6 3.4 4.6 3 2 3v9.5c2.6 0 4.6.4 6 1.5 1.4-1.1 3.4-1.5 6-1.5V3c-2.6 0-4.6.4-6 1.5zM8 4.5V14"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "preference":
    default:
      // sliders
      return (
        <svg {...common}>
          <path d="M2.5 5h1.6M7.9 5h5.6M2.5 11h6.1M12.4 11h1.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          <circle cx="6" cy="5" r="1.9" fill="none" stroke="currentColor" strokeWidth="1.4" />
          <circle cx="10.5" cy="11" r="1.9" fill="none" stroke="currentColor" strokeWidth="1.4" />
        </svg>
      );
  }
}

export function CategoryBadge({ category }: { category: Category }) {
  const meta = categoryMeta(category);
  return (
    <span className={`badge badge-${meta.id}`}>
      <CategoryIcon category={meta.id} />
      {meta.label}
    </span>
  );
}
