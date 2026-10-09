# Researchly: codebase and feature review — 9 October 2026

Review by **Codex (OpenAI)**, published at the maintainer's request. The application files in public revision [`47e4903`](https://github.com/amriitmohapatra/researchly-public/tree/47e490326ae3ea32fa1d452ccf90b49945d4d77e) match the source revision assessed on 9 October. Findings and validation below describe that historical review; publishing this document does not implement the recommendations or rerun the application suites. References to earlier findings are summarized here so this review stands alone.

Researchly has made substantial progress. The shared engine now supports a more complete coaching workflow: find a problem, understand it through a lesson, inspect the document's argument, and work through a reporting checklist. Most of yesterday's concrete failures have targeted fixes and regression coverage. The next priority should be making the new features' conclusions dependable, then improving the experience of revising a whole chapter. More rules or a learned critic should come after that work.

The main remaining problems are interpretation and state: a keyword becomes a completed checklist item; a rule that did not run becomes a zero in a progress chart; a resumed labelling session can count the same flag twice. The narrative map also needs the same restraint and genre awareness that the updated reviewer's brief has acquired.

## Scope and evidence

Reviewed the shared analysis pipeline, profiles, brief, argument and narrative modules, epidemiology packs, lesson delivery, hosted/local service adapters, website and Word workflows, progress storage and SQL policies, labelling/export/evaluation, printable reports, LSP changes, public-export tooling, and corresponding tests. Existing project plans informed the recommendations; this public edition omits links to internal planning documents.

Findings below distinguish executed synthetic reproductions from source inspection. All reproduction text was authored for this review. During the analysis, no production database was changed and no private manuscript was submitted to a hosted service. Local Python reproductions used Python 3.10, the shared `api.get_nlp()` pipeline and `en_core_web_sm`; targeted analysis disabled optional grammar/GEC tiers to isolate the relevant behavior.

## What changed since 8 October

| Previous finding | Reassessment at this revision |
|---|---|
| R1: local Word contract drift | Addressed for the reported options and missing explanations. `services/engine/tests/test_local_word_contract.py` invokes the actual local analysis handler with every current contract option and validates its JSON; shared `researchly/shapes.py` reduces future divergence. This is handler-level validation, not a real Word host/network test. |
| R2: Recommendations changes a manuscript into a policy brief | Addressed. Research headings take precedence; plain, Markdown and Word fixtures cover the case, and the response explains the guess. |
| R3: unsafe Word failure handling | Addressed for the reproduced field-probe and post-insertion failures. Field enumeration errors refuse the edit; Apply distinguishes applied, restore-failed, not-applied and unknown outcomes. Unit tests exercise these paths. Real-host behavior still needs validation. |
| R4: the brief treats silence as evidence | Addressed for the reported cases. Muted checks become “not assessed”; an excerpt without an Introduction makes no gap assertion; the brief abstains when no claims are detected and states its limits. |
| R5: unrelated evidence satisfies an entire section | Materially improved. Claims use all detected roles, a shared sentence parse and bounded evidence/reason windows; repeated section instances are separated in the argument model. Proximity remains a heuristic, so this does not establish that evidence actually supports a claim. |
| R6: website silently inherits Draft | Addressed by explicitly requesting Revise for website checks. This is a coherent choice for the revision studio; Word retains its stage control. |
| R7: LSP offsets and stale work | UTF-16 conversion, cancellation on close and a document-version check before publishing are implemented. Existing LSP tests pass. This is not proof against every scheduling race or editor integration issue. |
| R8: printed reports lose context | Addressed in the report model and rendering: checked/printed times, mode, profile, unavailable tiers, reading warnings, dismissed findings and stale-editor context are carried through. |

The additions worth preserving are the authored, cited lessons; session-only dismissal with Undo; checklist prompts that allow human judgment; opt-in progress with database enforcement; text-free label exports; and the separate public repository with an explicit export policy. These fit the product's coaching purpose. The qualifications below concern their implementation and interpretation.

## Findings to act on

Priority meanings: **P1** should be fixed before relying on the affected feature or publishing another affected export; **P2** should be scheduled in the next reliability pass. These are local observations, not estimates of how often users encounter them.

### N1 — P1: “Reported” overstates what checklist keyword matches establish

**Evidence:** [pack matching](packages/core/researchly/packs/__init__.py), lines 109–128, marks an item `reported` when *any* signal matches a sentence. [Epidemiology items](packages/core/researchly/packs/epidemiology.py) often ask compound questions but accept a single topic word.

Executed through `api.analyze(..., checklist="strobe")`:

```text
Methods

The sample size is not reported. Statistical analysis details are not
provided. Handling of missing data is not described.
```

The study-size, statistical-methods and missing-data items all become **reported**, with those sentences quoted as evidence. With PRISMA, `We searched PubMed.` completes the item asking for databases **and the date of the last search**, although no date is supplied.

This is a reporting inference error, independent of whether the underlying science is good. A writer can reasonably read “reported” and the tally as permission to move on. The reporting-only disclaimer does not resolve that mismatch.

**Recommendation:** initially call regex hits “possible reporting evidence” and ask the writer to confirm them. Split compound requirements into independently supported parts, and distinguish explicit absence, future promises and descriptions of previous studies. Preserve legitimate negative reports such as “There were no missing values”; simply rejecting every negation would also be wrong. Identify these as selected guideline themes, with guideline edition and item mappings, rather than implying full guideline compliance.

**Acceptance:** the two examples above remain unconfirmed/incomplete; genuine descriptions with the required details are found; legitimate negative reports, cited prior studies, table-only evidence and absent sections have explicit tests. Screen and print use the same cautious statuses.

### N2 — P2: progress can improve because a rule was muted or unavailable

**Evidence:** [progress rows](apps/web/lib/progress.ts), lines 32–40, store counts from returned suggestions, words and document type. [Trend construction](apps/web/lib/progress-view.ts), lines 49–68, substitutes zero whenever a rule is absent and combines all recorded checks. It has no record of whether the rule ran, was hidden, or was unavailable; even the stored document type is not used to separate comparisons.

Executed engine reproduction on unchanged Discussion text produced two `C303` suggestions, then zero with `disabled={"C303"}`. Executing the actual TypeScript trend function with two 1,000-word events, `{C303: 2}` followed by `{}`, produced rates `[2, 0]` and the label **“fewer.”** Preference visibility, Word Draft/Revise, profile changes and tier outages create similar ambiguities. Website control-triggered rechecks also record events even when the text has not changed.

**Recommendation:** record only the minimal, consented metadata needed to interpret counts: effective rule eligibility, mode, available tiers and an engine/ruleset version. Use “not assessed” gaps rather than zeros for ineligible rules. Compare compatible checks, expose article type and dates, and describe the view as flag frequency until it can support a learning interpretation. Do not introduce persistent document text or text fingerprints to solve this.

**Acceptance:** muting a rule, turning off preferences, changing mode/profile or losing grammar capability never creates a downward learning trend. Two comparable checks with an actually reduced count still do. Update the database constraints and privacy explanation together if metadata changes.

### N3 — P2: reloading mid-paragraph can duplicate labels and distort precision

**Evidence:** [LabelStudio](apps/web/components/pages/LabelStudio.tsx), lines 51–58, restores the session's labels but recreates `slots` as an empty object. [setVerdict](apps/web/lib/labels.ts), lines 99–106, can replace a verdict only if its slot survives. Exported labels contain no flag-instance identifier with which the evaluator could detect duplicates.

Executed the actual TypeScript functions: label a card Wrong, serialize/restore the session as a reload does, then label the same card Useful using the newly empty slot map. The export contains **both Wrong and Useful for paragraph 1 and the same rule**. The evaluator treats them as separate observations. The UI permits the corresponding flow: reload, paste the paragraph again, check and relabel. Editing/rechecking without moving to the next paragraph can also leave old labels behind when suggestion IDs change.

**Recommendation:** define a paragraph attempt lifecycle. Make partial work explicitly resumable or explicitly replace/discard the unfinished attempt before rechecking; ensure completed attempts cannot silently accumulate stale flags. If adding identifiers, use opaque attempt/instance IDs designed for this workflow, not a persisted hash of manuscript text. Retain the text-free export boundary.

**Acceptance:** exercise a real browser reload halfway through labelling, a changed verdict, edited text/recheck, multiple flags from the same rule, and an interrupted request. The evaluator must receive exactly the intended observations, with no accidental duplicates or orphaned labels.

### N4 — P2: two moves in one sentence are incorrectly “out of order”

**Evidence:** [narrative ordering](packages/core/researchly/discourse/narrative.py), lines 110–130, uses a strictly increasing sequence of sentence indices. A gap and an aim in one sentence have equal indices, so one cannot belong to that sequence.

Executed with the shared parse:

```text
Introduction

Although little is known about migration, we aimed to estimate annual flows.
```

The map marks the gap **present** and the aim **out_of_order**, with an empty explanatory note. The sentence explicitly gives the gap before the aim.

**Recommendation:** allow co-occurring moves at sentence granularity, or use within-sentence signal offsets only when they support an ordering judgment. Abstain when relative order is unknown. A sentence performing two rhetorical functions should not itself be a defect.

**Acceptance:** the example has no ordering warning; genuine reversed moves across separate sentences still receive useful, evidence-linked feedback; every displayed order warning has an explanation.

### N5 — P2: the narrative map ignores the selected genre's expectations

**Evidence:** [build_narrative](packages/core/researchly/discourse/narrative.py), lines 183–245, accepts `profile` but only writes its ID into the result. It chooses moves from the global section schemas. In contrast, [profiles](packages/core/researchly/profiles.py) explicitly sets `gap_expected=False` for response-to-reviewers and disables the manuscript gap rule.

Executed `api.analyze` with `document_type="response-to-reviewers"`, review and narrative enabled, on:

```text
Introduction

This response explains our changes.
```

The brief correctly has `gap_expected=False`; the map nevertheless reports a **missing research gap and aim**. The same result also marks “Why it matters” present merely because the first sentence has no other matched move. This exposes a broader wording issue: an opening fallback is not positive evidence that a rationale was supplied.

**Recommendation:** make applicability shared across the brief, rules and map. For unsupported genres, retain descriptive observations but abstain from manuscript-specific missing-move judgments. Prefer “not detected” to “missing” for lexical inference. Model whole document versus excerpt separately from genre. As the roadmap already proposes, add policy/reviewer-response structures only after authoring their own expectations.

Also inspect chapter boundaries: the narrative map groups by section *name*, while the updated argument model groups by section *instance*. Multiple Introduction or Discussion chapters should remain independently inspectable; one chapter's moves must not complete another's map. This latter concern is source inspection, not a separate executed chapter reproduction in this review.

**Acceptance:** explicitly selecting a response, commentary or policy brief changes all applicable structural judgments consistently; excerpts can abstain; repeated chapter sections remain separate; an arbitrary opening sentence is not presented as proof of a rationale.

### N6 — P1: permitted public-export archives bypass content checks

**Evidence from the maintainer’s release tooling:** the export gate accepts permitted binary extensions/paths and skips their contents before text-based checks. ZIP/DOCX contents are not unpacked for those checks. This tooling is not included in this public repository, so this finding records a release-process observation rather than a reproduction available from this checkout.

Executed a local synthetic gate reproduction: placed `REVIEW_SENTINEL_PRIVATE` in a compressed member of `demo/dist/check.zip` and `apps/web/public/demo/check.docx`, and supplied a policy that forbids that exact sentinel. The gate returned **no findings**. The same sentinel in a plain text file was correctly rejected. Third-party comparison was disabled for this isolated test; the private-term check remained active. The outcome was unchanged after installing and enabling gitleaks 8.21.2. This demonstrates a scan boundary gap, not an observed leak in the published repository.

**Recommendation:** either rebuild admitted demo artifacts exclusively from scanned, pinned source inputs and verify their hashes, or inspect ZIP/DOCX members with size/depth limits, including document metadata, comments and embedded text. Scan extracted text using the same policies. Keep audiovisual review explicit rather than implying text scanners validate a video's contents.

Two related source-inspection points belong in this release-hardening task: overlays are copied from the working directory, despite the claim that uncommitted content cannot be exported; and gitleaks is silently optional locally. Pin overlays and policy inputs to the chosen revision, reject overlay symlinks, and require the complete publication checks for a publish-ready export. CI installing gitleaks helps but does not give a local export the same guarantee.

**Acceptance:** a harmless forbidden sentinel in permitted ZIP/DOCX members is rejected; clean demo outputs pass; an uncommitted overlay edit cannot alter an export of an older ref; missing required scanners produce an explicit incomplete result. No automatic public push is needed to test any of this.

## Feature improvements worth prioritizing

These build on the existing roadmap rather than restarting it. “Done when” describes a useful product outcome, not simply a new component.

| Feature | Suggested next improvement | Done when |
|---|---|---|
| Revision workflow | Add the already-planned Correctness / Clarity / Whole-document passes, with grouped recurring findings and Next/Previous. Keep dismissal reversible and separate from globally muting a rule. | A writer can finish a chosen pass on a chapter without losing their position or overlooking hidden findings. |
| Checklist evidence | Add source positions and “Show in text”; support human confirmation and N/A consistently in website and Word. Word's current checklist component has no N/A control. | Every confirmed item has inspectable support or an explicit human decision, and print accurately preserves that distinction. |
| Narrative and brief | Fix N4/N5, then show the particular claim beside its candidate grounds and reason. Return spans/source locations, not only truncated quotes. | Repeated sentences, emoji and multi-file inputs jump to the intended evidence; unsupported assertions abstain. |
| Lessons | Keep the 26 authored, cited cards. Add optional short practice examples with an explanation of both a useful and an unnecessary edit; keep access possible without uploading text. | A writer can apply a principle to a fresh example, with no generative drafting or compulsory tracking. |
| Progress | Fix comparability before adding more charts. Show check date, scope, mode and why a point is excluded; let the writer choose comparable article types. | A downward line reflects fewer eligible flags, not a configuration change, and the view remains useful without a score. |
| Labelling and evaluation | Fix N3; pin an evaluation configuration and record version/settings metadata without text. The label page currently specifies Revise but leaves document type/account rule settings to normal resolution. Separate diagnostic rule accuracy from perceived coaching usefulness. | A saved report says exactly which engine and checks were evaluated, and rerunning the protocol produces comparable observations. |
| Files and coverage | Preserve the planned reading/omission summary, explicit main-TeX selection for ambiguous projects, and English-language scope. Add evidence locations that survive conversion. | Writers know whether notes, text boxes, figures and tables were assessed before interpreting silence. |
| Long-document behavior | Retain previous results while checking, show elapsed time, and make cancel/retry and stale results unambiguous. Avoid adding a new expensive pass before measuring it. | A large synthetic chapter can be cancelled and retried without losing text or showing an old response as current. |
| Account and local experience | Keep progress default-off and deletion independent of opting out. Complete the planned self-service account lifecycle and a local capability/connection summary. | Users can explain what leaves the machine, what is retained and how to delete it for each surface. |
| Demo and release | Make the demo an executable tour of both findings and limitations. Retain generated artifact/source consistency checks, strengthen the export gate, and record deployed engine/web/migration versions. | A release can be reproduced from a reviewed revision and its documented host checks, without conflating code merged with code deployed. |

For evaluation, Wilson intervals are a useful start, but flags within the same paragraph are correlated. Treat the current intervals as descriptive until there are enough independent paragraphs for a paragraph-clustered analysis. Report coverage by rule/section, unsure rates and sample counts; the fifty-paragraph exercise cannot establish recall or precision of checklist/narrative judgments it does not label. Add a small separate labelled set for those features, especially absence, negation, compound requirements and non-manuscript genres.

Correct the labelling guide's statement that paragraphs “never … leave the page”: the label **export** contains no text, but checking sends the paragraph to the configured engine, as the component itself documents. This distinction matters even though the main application's privacy architecture is deliberate.

## Validation performed during the original review

| Check | Result |
|---|---|
| Core, Python 3.10: `python -m pytest tests/ -q -rs` from `packages/core` | 918 passed, 2 skipped. |
| Hosted service suite and OpenAPI export check | 183 passed; contract up to date. |
| Website lint, confidentiality-boundary check, TypeScript and unit tests | Passed; 345 unit tests. |
| Contract TypeScript generation check | Passed. |
| Production-build browser suite | 152 passed, 7 skipped (opt-in screenshot cases). |
| Demo generation and label evaluator | 25 demo tests and 5 evaluator tests passed. |
| Maintainer release-tool tests (not shipped here) | 8 passed after installing gitleaks 8.21.2 in external tooling; its previously skipped test was rerun. |
| Targeted synthetic cases | Reproduced N1–N6 as described above, using the real relevant Python/TypeScript functions. |

The core skips cover the macOS Java-stub scenario and the opt-in remote LanguageTool-server test. Browser tests use installed system Chromium with production builds, mocked engine/Supabase responses and fake Office APIs; they are not real Microsoft Word, live account or deployed-engine validation. The browser executable differs from Playwright's pinned download. Demo requirements were installed into the external review virtual environment after the first demo run exposed missing `matplotlib`; repository dependency files were not changed.

PostgreSQL binaries were unavailable, so the updated two-user/RLS suite was inspected but **not independently rerun** here. The project's previously recorded Postgres 16 results are not counted as this review's results. No live migration/deployment, real Word acceptance test or large private corpus run was performed during the analysis. Existing green suites do not invalidate the new counterexamples: those scenarios are absent from the current coverage.

## Suggested implementation order

1. Correct checklist status semantics and public-export scan boundaries (N1/N6).
2. Make progress and labelling data interpretable before collecting more evaluation evidence (N2/N3).
3. Unify narrative applicability and fix same-sentence ordering (N4/N5).
4. Deliver the evidence-linked revision workflow, then run chapter-scale usability and real Word acceptance checks.
5. Use labelled results, with their limitations stated, to decide whether adding a learned critic offers enough benefit over improving the deterministic coach.
