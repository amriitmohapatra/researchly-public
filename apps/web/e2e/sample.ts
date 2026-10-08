/**
 * Sample document and suggestions for tests.
 *
 * Span offsets were computed in Python (str indices = Unicode code points),
 * exactly as the engine computes them. The text deliberately puts an emoji
 * (U+1F99F) and a non-BMP mathematical letter (U+1D445) before most spans,
 * so every span after them sits 1–2 UTF-16 units later in JavaScript.
 * tests/unit/fixtures.test.ts re-checks every span with an independent
 * code-point slice.
 */
import type { Suggestion } from "@researchly/contract";

export const SAMPLE_TEXT = "Introduction\nDengue 🦟 remains a major burden across South-East Asia. It is clearly proven that vector control reduces transmission.\n\nMethods\nThe samples were analysed using a renewal model. We utilize daily case counts, and 𝑅ₜ was estimated using a seven day window. Data was collected from 2019 to 2023 However the reporting delay varied.\n\nDiscussion\nIn order to understand the the dynamics of transmission, further studies are needed. This could potentially suggest seasonal forcing.\n";

export const SAMPLE_SUGGESTIONS: Suggestion[] = [
  {
    "id": "4fcbcef5e5a56b5c",
    "rule_id": "C201",
    "rule_name": "Booster overclaims certainty",
    "category": "improvement",
    "tier": "craft",
    "span": {
      "start": 75,
      "end": 89,
      "line": 2,
      "col": 63
    },
    "section": "introduction",
    "message": "‘clearly proven’ claims more certainty than a single body of evidence can carry.",
    "why": "Boosters such as ‘clearly’ and ‘proven’ close down discussion. In research writing, claims are calibrated to the evidence; readers trust a writer who signals confidence precisely rather than emphatically.",
    "plain": "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    "source": "Hyland (2005), Metadiscourse; The Craft of Scientific Writing §4",
    "learn_ref": null,
    "replacement": null,
    "fix_safety": "review",
    "confidence": 1.0,
    "text": "clearly proven"
  },
  {
    "id": "d9a653de4fa0f902",
    "rule_id": "P110",
    "rule_name": "Plain verb over Latinate verb",
    "category": "preference",
    "tier": "craft",
    "span": {
      "start": 193,
      "end": 200,
      "line": 5,
      "col": 53
    },
    "section": "methods",
    "message": "‘utilize’ can usually be ‘use’.",
    "why": "Shorter, more common verbs are easier to read. This is a matter of style, so it is offered as a preference only.",
    "plain": "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    "source": "Williams & Bizup, Style: Lessons in Clarity and Grace (ch. 7)",
    "learn_ref": null,
    "replacement": "use",
    "fix_safety": "safe",
    "confidence": 1.0,
    "text": "utilize"
  },
  {
    "id": "b791f4c642e4e7f9",
    "rule_id": "V305",
    "rule_name": "Compound adjective hyphen",
    "category": "convention",
    "tier": "craft",
    "span": {
      "start": 249,
      "end": 265,
      "line": 5,
      "col": 109
    },
    "section": "methods",
    "message": "Compound adjectives before a noun are usually hyphenated: ‘seven-day window’.",
    "why": "Most journal style guides hyphenate a compound modifier that precedes its noun, so readers parse it as one unit. This is a convention, not an error; follow your target journal.",
    "plain": "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    "source": "AMA Manual of Style §8.3; The Craft of Scientific Writing §9",
    "learn_ref": null,
    "replacement": "seven-day window",
    "fix_safety": "review",
    "confidence": 1.0,
    "text": "seven day window"
  },
  {
    "id": "da107cbdab95b166",
    "rule_id": "V310",
    "rule_name": "‘Data’ as a plural noun",
    "category": "convention",
    "tier": "craft",
    "span": {
      "start": 267,
      "end": 275,
      "line": 5,
      "col": 127
    },
    "section": "methods",
    "message": "Many journals treat ‘data’ as plural: ‘data were’.",
    "why": "Usage is divided. Biomedical journals mostly keep ‘data’ plural; others accept the singular. Check your target journal and be consistent.",
    "plain": "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    "source": "AMA Manual of Style §7.8",
    "learn_ref": null,
    "replacement": "Data were",
    "fix_safety": "review",
    "confidence": 1.0,
    "text": "Data was"
  },
  {
    "id": "a8c0e1a16e3facaf",
    "rule_id": "G110",
    "rule_name": "Missing sentence boundary",
    "category": "correction",
    "tier": "craft",
    "span": {
      "start": 303,
      "end": 303,
      "line": 5,
      "col": 163
    },
    "section": "methods",
    "message": "A sentence seems to end after ‘2023’ without punctuation.",
    "why": "Two independent clauses run together without a full stop or semicolon. Readers stumble at the join.",
    "plain": "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    "source": "The Craft of Scientific Writing §2 (sentence boundaries)",
    "learn_ref": null,
    "replacement": ".",
    "fix_safety": "review",
    "confidence": 1.0,
    "text": ""
  },
  {
    "id": "4cbb67bca50f2590",
    "rule_id": "C120",
    "rule_name": "Wordy phrase",
    "category": "improvement",
    "tier": "craft",
    "span": {
      "start": 352,
      "end": 363,
      "line": 8,
      "col": 1
    },
    "section": "discussion",
    "message": "‘In order to’ can usually be ‘To’.",
    "why": "‘In order to’ adds two words without adding meaning; cutting it moves the reader to the verb sooner.",
    "plain": "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    "source": "Williams & Bizup, Style (ch. 6: Concision)",
    "learn_ref": null,
    "replacement": "To",
    "fix_safety": "safe",
    "confidence": 1.0,
    "text": "In order to"
  },
  {
    "id": "efaf788eeaab0edb",
    "rule_id": "S010",
    "rule_name": "Repeated word",
    "category": "correction",
    "tier": "spelling",
    "span": {
      "start": 375,
      "end": 382,
      "line": 8,
      "col": 24
    },
    "section": "discussion",
    "message": "‘the’ is repeated.",
    "why": "A doubled word is almost always a slip made while revising.",
    "plain": "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    "source": "Spelling tier: repeated-token check",
    "learn_ref": null,
    "replacement": "the",
    "fix_safety": "safe",
    "confidence": 1.0,
    "text": "the the"
  },
  {
    "id": "d2cfdb7e73c22d70",
    "rule_id": "D401",
    "rule_name": "Vague call for further research",
    "category": "improvement",
    "tier": "lens",
    "span": {
      "start": 409,
      "end": 435,
      "line": 8,
      "col": 58
    },
    "section": "discussion",
    "message": "Say what further study would resolve, rather than that one is needed.",
    "why": "Examiners read ‘further studies are needed’ as filler. A specific next step (which data, which design) shows you understand the limits of your own work.",
    "plain": "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    "source": "Wallace & Wray (2016), Critical Reading and Writing for Postgraduates, ch. 7",
    "learn_ref": null,
    "replacement": null,
    "fix_safety": "review",
    "confidence": 1.0,
    "text": "further studies are needed"
  },
  {
    "id": "4b3c0e2c0b1c1a15",
    "rule_id": "C205",
    "rule_name": "Stacked hedges",
    "category": "improvement",
    "tier": "craft",
    "span": {
      "start": 442,
      "end": 467,
      "line": 8,
      "col": 91
    },
    "section": "discussion",
    "message": "Three hedges in a row (‘could’, ‘potentially’, ‘suggest’) make the claim hard to read.",
    "why": "One well-placed hedge signals appropriate caution; stacking them reads as evasive. Keep the hedge that matches your evidence.",
    "plain": "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    "source": "Hyland (1998), Hedging in Scientific Research Articles",
    "learn_ref": null,
    "replacement": null,
    "fix_safety": "review",
    "confidence": 1.0,
    "text": "could potentially suggest"
  },
  {
    "id": "0aa528d9b7620edc",
    "rule_id": "P120",
    "rule_name": "Intensifier adverb",
    "category": "preference",
    "tier": "craft",
    "span": {
      "start": 448,
      "end": 459,
      "line": 8,
      "col": 97
    },
    "section": "discussion",
    "message": "‘potentially’ may be redundant next to ‘could’.",
    "why": "Modal verbs already express possibility. A matter of taste, so shown only when you ask for preferences.",
    "plain": "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    "source": "Williams & Bizup, Style (ch. 6)",
    "learn_ref": null,
    "replacement": "",
    "fix_safety": "review",
    "confidence": 1.0,
    "text": "potentially"
  }
];
