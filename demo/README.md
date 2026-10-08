# Researchly demo manuscript

A short, made-up paper written to show Researchly at work: an SEIR model
fitted to one dengue season in three fictional districts of a fictional
country. The writing is meant to be good scientific prose, with a proper
IMRaD structure, two numbered equations, one table of districts and one of
parameter estimates, two figures and a short author-year reference list,
**plus seventeen deliberate errors** that the engine should flag and
nothing else. That is the point of the demo: every card the reader sees is
a planted one, so the demo shows precision as much as coverage.

Everything in it is invented: the country (Velmora), the districts
(Marrowick, Tessvale, Oldmere), the authors, the institute, the numbers,
the journals and every reference. Nothing is quoted from any paper, thesis,
course or guide.

## Files

| Path | What it is |
|---|---|
| `manuscript.py` | The ONE source of truth: title, abstract, sections, equations, tables, figure data, references. |
| `build_demo.py` | Renders the manuscript into the three formats below (and draws the figures). |
| `dist/researchly-demo.docx` | Word version: real Heading 1/2 styles, Caption style on captions, a real Word table for each table, PNG figures, equations as Office Math (OMML). |
| `dist/researchly-demo-overleaf.zip` | Overleaf project: `main.tex` with `\input{sections/*.tex}`, `figures/*.png`, `references.bib` (natbib, `\citep`/`\citet`), `equation`/`table`/`figure` environments with `\label`/`\ref`. |
| `dist/researchly-demo.md` | Plain Markdown of the same text, for the website's text box. |
| `dist/figures/*.png` | The two figures (600 px wide, 100 dpi, under 40 KB each). |
| `tests/test_demo.py` | Proves every planted error fires in each format where it can, that nothing else fires, and that the three versions carry the same prose. |

## Rebuilding

```
python3.10 demo/build_demo.py            # writes demo/dist/
python3.10 -m pytest demo/tests -q       # from the repository root
```

Needs `python-docx`, `lxml` and `matplotlib` beside the engine's own
dependencies. The Overleaf zip is ordinary LaTeX (`article`, `amsmath`,
`graphicx`, `booktabs`, `natbib`); it is not compiled by the build.

Edit the text in `manuscript.py` only. The test fails if a planted error
stops firing or a new, unplanted flag appears, so after a wording change
run the tests and tune the prose until it is clean again. Tune the prose,
never the engine.

## Using the demo

- **Website**: upload `dist/researchly-demo.docx` or
  `dist/researchly-demo-overleaf.zip` as a file, or paste the contents of
  `dist/researchly-demo.md` into the text box. Turn on "show preferences"
  to see everything the test counts.
- **Word add-in**: open `dist/researchly-demo.docx` in Word and run the
  add-in. The equations are real equation objects, the captions use Word's
  Caption style and the tables are real tables, so the structural checks
  (uncited table, out-of-order figures, the number missing from Table 1,
  the equation after a full stop) all work in Word as well as on upload.
- **Overleaf**: upload the zip to Overleaf as a new project; it compiles
  as it is (one `\ref` is deliberately broken and prints as "??").

## The planted errors

Seventeen, each exactly once, each in a sentence that otherwise reads well.
"Where" names the section and the words the flag sits on. The Markdown
version has no figures, tables or equation objects, so the structural rules
(X1xx, X2xx, X3xx, X4xx) cannot apply to it; the eleven prose errors do.

| # | Where | What is wrong | Rule | .docx | .zip | .md |
|---|---|---|---|---|---|---|
| 1 | Abstract, first sentence (the card anchors there) | The abstract has background, gap, aim, methods and findings but no significance move. | AB802 | yes | yes | yes |
| 2 | Introduction: "Transmission **is known to** be sensitive to temperature..." | A consensus claim with no citation in the sentence. | E704 | yes | yes | yes |
| 3 | Introduction: "most of them with **an** renewal model" | "an" before a consonant sound. | LT001 (LanguageTool, grammar tier) | yes | yes | yes |
| 4 | Methods, Study setting: "we treated **the the** week of the clinic visit" | Doubled word. | W207 | yes | yes | yes |
| 5 | Methods, Transmission model: "the extrinsic incubation period (**EIP**)" | The abbreviation was already defined in the Introduction. | F612 | yes | yes | yes |
| 6 | Methods, Transmission model: Equation (2), after "...the ratio of these rates**.**" | A displayed equation that starts after a full stop instead of being led in. Equation (1) shows the right way. | X302 | yes | yes | n/a |
| 7 | Methods, Statistical inference: "we ran a **seperate** fit" | Spelling. | S001 | yes | yes | yes |
| 8 | Results, first paragraph: "(**Figure 1**)" after "(Figure 2)" | Figure 2 is cited before Figure 1. | X102 | yes | yes | n/a |
| 9 | Results, first paragraph: "**Figure 1 shows** that all three districts..." | A sentence that opens with the display instead of the finding. | E707 | yes | yes | yes |
| 10 | Results, second paragraph: "The attack rate was **4.8%** in Marrowick ... (Table 1)" | Table 1 says 4.2%. | X401 | yes | yes | n/a |
| 11 | Results, second paragraph: "differences in **transmision**" | Spelling. | S001 | yes | yes | yes |
| 12 | Results, Figure 1's caption: "Weekly reported dengue cases." | Four words: the figure cannot be read on its own. | X202 | yes | yes | n/a |
| 13 | Results, Table 2 (posterior estimates) | Never cited anywhere in the text. | X101 | yes | yes | n/a |
| 14 | Discussion: "A similar lead ... **was shown by Lim and colleagues** (2021)" | Passive voice with the agent named (never flagged in Methods). | G104 | yes | yes | yes |
| 15 | Discussion: "This **proves** that housing density explains..." | Overclaiming. | C302 | yes | yes | yes |
| 16 | Discussion: "The lag between the peaks ... (**Figure 3**)" / `\ref{fig:missing}` | A cross-reference to a figure that does not exist (there are two). | X103 | yes | yes | n/a |
| 17 | Discussion: "**may possibly** suggest that the virus moved outward" | Two hedges stacked. | C301 | yes | yes | yes |

Two choices worth knowing about:

- X101 is planted on **Table 2**, not a figure. With exactly two figures,
  Figure 2 has to be cited before Figure 1 for X102, so both figures are
  cited; the never-cited float is therefore the parameter table, which is
  also the float authors most often forget.
- F612 uses **EIP**, not R0: the engine's definition detector needs an
  abbreviation with at least two capitals, and "R0" has one.

## Final counts (engine run at build time, all tiers on, preferences shown)

| Format | Words the engine sees | Flags | Planted | Unplanted |
|---|---|---|---|---|
| `.docx` | 1,656 | 17 | 17 | 0 |
| `.zip` (Overleaf) | 1,584 | 17 | 17 | 0 |
| `.md` | 1,656 | 11 | 11 | 0 |

The prose itself (abstract and body paragraphs, without title, captions,
tables and references) is 1,536 words. The test allows up to 12 unplanted
flags per 1,000 words and asserts the exact total, so any drift shows up.
The LT001 row needs the grammar tier (local LanguageTool, which needs
Java); the test skips that one assertion when the tier is unavailable.
