# Real-document test bench: sources

`manifest.yaml` lists **219 openly licensed documents** for the CI harness to fetch at run
time: 178 research documents and 41 Word robustness test files. The texts are never
committed; only metadata is. Every item's licence was checked one by one (2026-10-03;
the 11 PMC-mirrored preprints 2026-10-04),
and each row in `manifest.yaml` records where the licence was seen. The registry entries
are the seven `realdocs-*` ids in `ml/datasets.yaml`.

## Counts

**Research documents by discipline × source**

| Discipline | PMC JATS | PMC .docx supp | med/bioRxiv | GitHub LaTeX | Total |
|---|---|---|---|---|---|
| epidemiology (infectious disease, modelling) | 34 | 5 | 7 | 1 | 47 |
| public-health | 9 | 3 | 3 | – | 15 |
| clinical-medicine | 13 | 6 | – | – | 19 |
| molecular-biology | 13 | 1 | – | – | 14 |
| ecology-evolution | 13 | 2 | 3 | 3 | 21 |
| physical-earth-sciences | 10 | – | – | 1 | 11 |
| engineering | 2 | – | – | 2 | 4 |
| computational-statistics | 11 | – | 1 | 8 | 20 |
| social-sciences | 10 | 3 | – | 1 | 14 |
| humanities | – | – | – | 2 | 2 |
| **Total** | **115** | **20** | **14** | **18** | **167** |

Plus 11 medRxiv/bioRxiv preprints mirrored in PMC (P30): 5 epidemiology, 4 molecular
biology, 2 neuroscience (ids `pmcpreprint-*`; see below).

**By licence**

| Licence | Items | permitted_use |
|---|---|---|
| CC-BY-4.0 | 167 (112 JATS, 20 docx, 20 preprints, 15 LaTeX) | ci_eval, train_experimental |
| CC0-1.0 | 7 (3 JATS, 1 preprint, 3 LaTeX) | ci_eval, train_experimental |
| CC-BY-ND-4.0 / CC-BY-NC-ND-4.0 / CC-BY-NC-4.0 | 2 / 1 / 1 (preprints) | ci_eval only (D2) |
| Apache-2.0 / MPL-2.0 / BSD-2-Clause / MIT | 24 / 12 / 3 / 2 (test files) | ci_eval only |

**PMC JATS by article type:** 105 research articles, 3 randomised controlled trials, and
7 reviews (2 narrative, 2 systematic, 2 scoping, 1 systematic review with meta-analysis).
Years: 2022 (14), 2023 (13), 2024 (28), 2025 (74).

**PMC JATS by journal:** PLOS ONE 65, PLOS Comput Biol 27, PLOS NTD 5, PLOS Pathog 4,
PLOS Genet 4, PLOS Med 3, PLOS Glob Public Health 3, PLOS Biol 2, eLife 2 (both CC0).

## How the items were found

**PMC (PubMed connector).** I searched with `search_articles`, always adding
`pubmed pmc open access[filter]` and a 2018/2019–2025 date range. Queries used:

- Epidemiology: `(transmission model[Title/Abstract] OR reproduction number[Title/Abstract]) AND (PLoS Comput Biol OR Nat Commun OR BMC Med OR PLoS Med OR eLife)[journal]`
- Epidemiology: `(dengue OR malaria OR influenza OR measles OR tuberculosis)[Title] AND (model OR modelling OR modeling)[Title]` in PLOS Comput Biol / PLOS NTD, 2018–2022
- Reviews: `Review[Publication Type] AND (epidemic OR transmission OR vaccine OR modelling)`
- Public health: `public health / health inequalities / health policy / tobacco / obesity [Title]` in PLOS Glob Public Health / PLOS Med / PLOS ONE
- Clinical medicine: `(randomized controlled trial[pt] OR cohort[Title]) AND patients[Title]`
- Molecular biology: `protein / gene expression / signaling / chromatin [Title]` in PLOS Biol / Genet / Pathog, and an eLife cell-biology query
- Ecology: `biodiversity / species richness / phylogenetic / population dynamics / habitat [Title]`
- Earth and physical sciences: `earthquake, rainfall, groundwater, soil erosion, climate change, glacier, solar, nanoparticles` and `seismic, precipitation, aquifer, sediment, atmospheric, landslide, permafrost, hydrological [Title]`
- Computation and statistics: `Bayesian, statistical method, machine learning, simulation study, software, R package [Title]`
- Social sciences: `social capital, income inequality, migration, voting, education, unemployment, sociology, political, household income, social media [Title]`

Every hit then went through `get_copyright_status`, and `get_article_metadata` supplied the
title, year and article type. I assigned disciplines from the titles.

**Word supplements.** I pulled the PMC full-text records (`get_full_text_article`) for
71 PLOS candidates. PLOS lists each supporting file with a format tag such as
`(DOCX)`, so I kept the 20 articles that had at least one .docx supplement. No article
text was saved.

**Preprints (bioRxiv connector).** I ran `search_preprints` by date window and category
(medRxiv epidemiology, 1–10 March 2024; bioRxiv ecology and evolutionary biology,
1–3 May 2024), then called `get_preprint` on each candidate to read its `license` and
`jatsxml` fields. Of 29 preprints checked, 10 were `cc_by`. 4 NC/ND ones were kept as
ci_eval only; 3 `cc_no` and 12 further NC/ND ones were left out.

**Preprints mirrored in PMC (P30, 2026-10-04).** medRxiv and bioRxiv refused 11 of the
14 downloads above in GitHub Actions. NIH-funded preprints are also deposited in PMC (the
NIH Preprint Pilot), where Europe PMC serves them like any other article. I searched
PubMed for `preprint[pt] AND (transmission[tiab] OR epidemiolog*[tiab]) AND free full
text AND (medRxiv[journal] OR bioRxiv[journal])` from 2022, read the PMC licence of the
40 newest with `get_copyright_status`, and kept the 10 CC BY 4.0 and 1 CC0 ones (5
infectious-disease epidemiology, 6 biology). None of the original 14 had a PMC copy
(`convert_article_ids`), so they stay in the manifest as a weekly check on the servers.

**LaTeX.** I used GitHub repository search (`license:cc-by-4.0 language:TeX paper`,
`... manuscript`, `license:cc0-1.0 language:TeX paper`). For each repository I took a
blobless clone to pin the commit and list the `.tex` files, then read the LICENSE file
raw at that commit. I kept only human-written manuscripts of papers or books.

**Test files.** I took blobless clones of `apache/poi`, `LibreOffice/core`,
`python-openxml/python-docx` and `mwilliamson/mammoth.js`, chose files by feature, and
pinned each to a commit SHA.

## What was excluded, and why

- **Nature Communications, BMC Medicine, and eLife papers that are not CC0.** The connector
  returned only "© The Author(s)" with no licence, so the licence was never seen. This
  affected 27 hits.
- **arXiv (the planned `latex` source).** `arxiv.org` is blocked for both the shell and web
  fetch, and search results do not show per-paper licences. No arXiv licence could be
  verified first-hand, so the 18 GitHub-hosted manuscript sources replace it.
- **Non-research items:** 4 published errata, and two items authored by "The PLOS ONE
  Staff" or "The PLOS One Editors" (presumed journal notices).
- **Near-duplicates:** 2 papers on "green synthesis" of nanoparticles; one of that type is
  kept.
- **Preprints** licensed `cc_no` (no reuse), plus most NC/ND preprints. Only 4 NC/ND
  infectious-disease or statistics preprints are kept, for evaluation only.
- **GitHub repositories:** those with no LaTeX manuscript (R Markdown only); templates;
  slide decks; 2026 "living papers" that look machine-generated; and an English
  translation of a third-party 1971 paper, whose CC BY claim cannot cover the original.
- **Apache POI test documents crawled from the web** (file names containing domain names),
  because the provenance of their content is unclear.

## Caveats for whoever uses this next

- **Licence versions.** PLOS statements and the bioRxiv API's `cc_by` value give no
  version. The 4.0 version comes from the publisher's licence policy, not from each item.
  The permissions are the same under every CC BY version.
- **GitHub LaTeX sources** are the authors' manuscripts, not the publishers' versions.
  Their `year` is the date of the pinned commit.
- **Test files** carry only the repository's licence and are not prose, so they are never
  training data.
- **Before any `ship_*` use,** S5a needs an attribution plan, because CC BY requires
  attribution on every shipped sentence.
