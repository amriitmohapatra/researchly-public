# Researchly v0.1 — prototype

A research-focused writing checker: typed, explainable, **section-aware**
suggestions for scientific prose. Built for personal use first (thesis
chapters, papers, Quarto/R Markdown, LaTeX).

This is the Phase-3 thin slice agreed after the landscape research (see
`../research/00-synthesis.md`): ~24 rules derived from
`The-Craft-of-Scientific-Writing.md` (full mapping in
`../docs/rule-inventory.md`), a markup-masking layer, IMRaD section
detection, and a CLI.

## What makes it different from a grammar checker

- **Typed suggestions.** Every flag is a `correction` (objectively wrong),
  `improvement` (clearer alternative), `convention` (how scientific writing
  is done — labeled as such, never as an error), or `preference`
  (subjective — hidden by default).
- **Section-aware.** Passive voice is *never* flagged in Methods. Causal-verb
  and overclaiming checks only run in Abstract/Results/Discussion. The same
  sentence gets different advice in different sections — detected from your
  headings.
- **Explains itself.** Every rule carries the reasoning from the writing
  guide (`--explain`, or `researchly explain G101`). The point is to teach,
  not just to flag.
- **Markup-safe.** Quarto/R Markdown/LaTeX are masked (code chunks, math,
  `@citations`, `\cite{}`, front matter) with character positions preserved,
  so nothing inside markup is ever flagged and every location maps exactly
  to your source file.
- **Precision over recall.** Conservative lexicons, technical-usage
  exemptions ("novel coronavirus" is not hype; "Garcia et al." is not a
  noun string), agentless passives never flagged.

## Install

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Python ≥ 3.9. On Python < 3.11, `.researchly.toml` config support needs the
small `tomli` package (included in `requirements.txt`; everything else works
without it). No other dependencies; everything runs locally — nothing leaves
your machine.

## Use

```bash
cd prototype

python -m researchly check demo/sample.qmd            # check a file
python -m researchly check chapter.tex --explain      # with full rationales
python -m researchly check draft.md --all             # include preferences
python -m researchly check draft.md --disable W203,G106
python -m researchly check draft.md --json            # machine-readable
python -m researchly rules                            # list all rules
python -m researchly explain C303                     # one rule, in full
python -m researchly stats                            # which rules earn their keep (local usage data)
```

Per-project muting — put `.researchly.toml` next to your files:

```toml
[rules]
disable = ["W203"]        # this journal likes "novel", fine
show_preferences = false
```

Exit code is 1 when suggestions exist (usable in a Makefile/CI).

## The rule pack (v0.1)

Sentence mechanics (Gopen & Swan): G101 subject–verb separation
(interruption-based) · G102 buried action · G103 nominalization density ·
G104 passive-with-agent (silent in Methods) · G105 expletive openers ·
G106 overlong sentence (>50 words) · G107 noun strings · G108 weak stress
position.

Thresholds and guards were calibrated against a corpus of 8 accepted PhD
theses in infectious disease modelling (see `../docs/dogfooding-report.md`)
— e.g., technical compounds ("Markov chain Monte Carlo") are never noun
stacks, purpose infinitives ("to prevent transmission") are never causal
claims, and repeated causal verbs aggregate into one suggestion per section.

Words and tone: W201 grand words · W202 wordy phrases · W203 hype ·
W204 intensifiers (pref) · W205 filler · W206 redundant pairs ·
W207 doubled words · W208 contractions · W209 "in terms of" (pref).

Calibration and claims: C301 hedge stacking · C302 overclaiming ·
C303 causal verbs (design-check prompt) · C304 bare "significant" ·
C305 assertive adverbs · F601 undefined acronyms.

From the owner's lecture and course notes and Shehzad
2008 — provenance in `../docs/knowledge-base.md`): E701 empty phrases ·
E702 adversative runs · E703 naked "This" · E704 uncited "is known to be" ·
E705 absolute novelty claims · E706 "relatively" without comparator ·
E707 "Figure 1 shows…" openers (Results) · AB801 vague abstract
forward-references · L901 serial-summary lit-review openers · D902 missing
gap statement in the Introduction (document-level).

The commodity layer (integrated open source, still no LLM):

- **S001 spelling** — SymSpell (symspellpy, MIT) with scientific-vocabulary
  guards: a shipped lexicon (seroprevalence, covariates, nowcasting, Aedes
  aegypti…), UK/US variants, morphology, proper-noun/acronym skips, and
  terms you use 3+ times are treated as yours. Teach it your words:
  `researchly dict add <word>` (stored locally).
- **LT001 grammar** (optional) — agreement, verb forms, a/an, word
  confusions via a LOCAL LanguageTool server (open source, non-AI):
  `pip install language-tool-python` + Java 17+. Absent = silently off;
  spelling and style categories filtered so tiers never double-flag.

Plus a document metrics read-out (deliberately not a score): sentence
lengths, nominalization and hedge density, passive share *by section*.

## Layout

```
researchly/
  document.py     markup masking (offset-preserving) + section detection
  engine.py       Suggestion/Rule types, registry, check pipeline
  lexicons.py     curated word lists (auditable, easy to extend)
  rules_lexical.py  regex/lexicon rules
  rules_syntax.py   spaCy dependency-based rules
  metrics.py      document read-out
  cli.py          terminal interface
tests/            fire / don't-fire tests for every rule
demo/sample.qmd   seeded demo document
```

## Adding a rule

Add a function in `rules_lexical.py` or `rules_syntax.py` with the
`@rule(...)` decorator (id, name, category, short description, "why" text,
optional section conditions), yield `Suggestion(message, start, end,
replacement)` objects with offsets into `document.masked` (identical to
source offsets), and add a fire + don't-fire test. Word lists live in
`lexicons.py`.

## Known limitations (v0.1)

- Regex-based LaTeX masking: exotic macros or deeply nested braces may leak
  or over-mask. Fine for typical article/thesis source.
- Section detection is heading-keyword based; unusual heading names fall
  back to "other" (section-restricted rules then stay quiet — conservative
  by design). Unheaded snippets are section "unknown" (everything fires).
- `en_core_web_sm` misparses occasionally; rules are tuned so parser errors
  produce silence rather than false flags, but not perfectly.
- English only. No grammar-proper checks (agreement, articles) — that's
  commodity (LanguageTool/Harper); Researchly differentiates instead.

## Integrations

- **Word add-in** — `word-addin/` (sidebar in MS Word, local server).
- **VS Code / Positron / any LSP editor** — `vscode-extension/` (bundled
  extension) + `python -m researchly.lsp` (the language server itself).
- **Usage telemetry (local-only)** — the Word add-in logs
  shown/goto/apply/dismiss/mute events to `~/.researchly/telemetry.jsonl`
  on this machine only; `python -m researchly stats` reports per-rule keep
  rates so tuning follows your actual behavior. Delete the file anytime to
  reset.

## Where this goes next (per the synthesis)

Hedging/certainty meter upgrade → terminology-consistency (W210/F605) →
LLM "review lens" for paragraph/document-level feedback (CARS moves,
Toulmin audit).
