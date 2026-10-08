/**
 * The Learn cards (S4c): looked up from a result's `learn_ref`, grouped in
 * the engine's order for the lessons pages, and found for a rule. The cards
 * are authored in packages/core/researchly/learn.py and ship with the
 * contract as LEARN_CARDS (packages/contract/learn.json): static data, so
 * opening one sends nothing anywhere. Pure and unit-tested.
 */
import { LEARN_CARDS, type LearnCard } from "@researchly/contract";

const BY_ID: ReadonlyMap<string, LearnCard> = new Map(LEARN_CARDS.map((c) => [c.id, c]));

/** Where every lesson is listed. Opened in a new tab so the results stay where they are. */
export const LEARN_PATH = "/learn";

/** The card a `learn_ref` names, or null when there is none (or this build does not know it). */
export function learnCard(ref: string | null | undefined): LearnCard | null {
  if (typeof ref !== "string" || !ref.trim()) return null;
  return BY_ID.get(ref.trim()) ?? null;
}

/** The groups in the engine's order (learn.py GROUPS); a group the site does not know yet goes last. */
export const LEARN_GROUPS = [
  "Sentences",
  "Words",
  "Claims and evidence",
  "Figures, tables and numbers",
  "Structure and argument",
  "Mechanics",
] as const;

export function groupedCards(cards: readonly LearnCard[] = LEARN_CARDS): { group: string; cards: LearnCard[] }[] {
  const order = new Map<string, number>(LEARN_GROUPS.map((g, i) => [g, i]));
  const groups = new Map<string, LearnCard[]>();
  for (const c of cards) {
    const list = groups.get(c.group) ?? [];
    list.push(c);
    groups.set(c.group, list);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (order.get(a) ?? LEARN_GROUPS.length) - (order.get(b) ?? LEARN_GROUPS.length))
    .map(([group, list]) => ({ group, cards: list }));
}

export function cardById(id: string, cards: readonly LearnCard[] = LEARN_CARDS): LearnCard | null {
  return cards.find((c) => c.id === id) ?? null;
}

/** The lesson for a rule: the registry's own `learn_ref` when it names a card, else the first card listing the rule. */
export function cardForRule(
  ruleId: string,
  learnRef: string | null | undefined,
  cards: readonly LearnCard[] = LEARN_CARDS,
): LearnCard | null {
  if (learnRef) {
    const byRef = cardById(learnRef, cards);
    if (byRef) return byRef;
  }
  return cards.find((c) => (c.rules ?? []).includes(ruleId)) ?? null;
}

export function lessonHref(card: Pick<LearnCard, "id">): string {
  return `/learn/${encodeURIComponent(card.id)}`;
}
