# Researchly

A writing coach for research writing. It checks a draft the way a careful
reader would, explains every point, says where the advice comes from, and
leaves every change to you. It never writes for you.

Try it at **[researchly-chi.vercel.app](https://researchly-chi.vercel.app)**,
on your own draft or on the made-up demo paper.

[![Researchly in about a minute: play the video](media/researchly-video.png)](media/researchly-video.mp4?raw=true)

*Researchly in about a minute (click to play). The paper in it is the
made-up demo paper in `demo/`, with 17 mistakes planted on purpose. The
narration is a synthetic voice (Kokoro, an open-source text-to-speech
model).*

## Why

Feedback on scientific writing usually arrives late, after a draft has gone
to a supervisor or a reviewer, and no two readers give the same advice.
Grammar checkers stop at the sentence; generative tools write the text for
you. Researchly reads the whole draft and shows what a careful reader would
notice.

- **Same draft, same advice.** With the same settings, the same text gets
  the same feedback: the checks are written rules, not a generative model.
- **A source for every suggestion.** Each flag says what was noticed, why it
  matters in plain words, and where the advice comes from.
- **No cloud or generative AI reads your draft.** The text is processed in
  memory for one request by Researchly's own engine and then dropped. A
  local mode that sends nothing anywhere is available for the Word add-in.
- **It never writes for you.** No drafting, rewriting or paraphrasing, so it
  fits where generative AI is restricted.
- **Section-aware.** The same sentence gets different advice in Methods and
  in the Discussion: passive voice is expected in Methods.
- **Checks across the whole draft.** Figures and tables cited in order,
  abbreviations defined once, numbers in the text found in the table they
  cite, equations that belong to sentences.

Beyond sentences, it gives a reviewer's brief (the questions a critical
reader asks, with the sentences each answer rests on), a narrative map
(which moves each section makes and which are missing), short lessons, and
reporting checklists for epidemiology (STROBE, CONSORT, PRISMA, EPIFORGE)
that check reporting, never the science.

## Four kinds of suggestion

| Kind | Meaning |
|---|---|
| Correction | Likely an error. Worth fixing. |
| Improvement | Correct, but clearer if revised. |
| Convention | A norm of research writing; never presented as an error. |
| Preference | A matter of taste. Hidden unless you switch it on. |

## What is here

| Folder | Contents |
|---|---|
| `packages/core/` | The engine: the `researchly` Python package, its rules, lessons and tests |
| `packages/contract/` | The API contract (OpenAPI and TypeScript types) every surface uses |
| `services/engine/` | The hosted engine service (FastAPI, with a LanguageTool sidecar) |
| `apps/web/` | The website and the Word taskpane (Next.js) |
| `apps/word-addin/` | Word add-in manifests and the local engine server |
| `apps/vscode-extension/` | Language server client for VS Code and Positron |
| `apps/desktop-mac/`, `apps/desktop-win/` | Desktop apps (maintenance only) |
| `supabase/` | Database migrations for optional accounts, and their two-user tests |
| `demo/` | A made-up paper with 17 planted mistakes, as Word, Overleaf and Markdown |
| `ml/realdocs/` | A bench that runs the engine on openly licensed articles |
| `ml/eval/` | Precision from labelled flags |

## Run it

The engine is tested on Python 3.10 and 3.11.

```bash
cd packages/core
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m pytest tests/ -q
python -m researchly check path/to/draft.md
```

The grammar tier uses a local LanguageTool, which needs Java. Without Java
that tier reports itself as off rather than failing silently.

The engine service and the website, in two terminals:

```bash
cd services/engine
pip install -r requirements-dev.txt
RESEARCHLY_ENV=development python -m researchly_service   # :8080

cd apps/web
npm ci
NEXT_PUBLIC_ENGINE_URL=http://localhost:8080 npm run dev  # :3000
```

The hosted setup (Cloud Run, Vercel, Supabase) is deployed from the private
repository; `services/engine/README.md` shows how to run the service.

## Where the advice comes from

Every rule names its source on the card. The sources are published works
(for example Gopen and Swan on reader expectations, Swales on research
introductions, Toulmin on argument, Wallace and Wray on critical reading,
and the reporting guidelines), Researchly's own writing guide, and the
maintainer's notes from scientific-writing training. Sources are cited and
paraphrased; no third-party passage is reproduced.

## About this repository

This public repository is generated from a private one. The private
repository also holds evaluation material that cannot be redistributed:
accepted theses used to measure how often the engine flags good writing,
and course notes used to check that no third-party text ships. Those
measurements are reported, but they cannot be reproduced from here. The
real-document bench in `ml/realdocs/` uses openly licensed articles and can.

Comments in the code sometimes mention `CLAUDE.md`, `PLAN.md`,
`ARCHITECTURE.md` or the project log. Those are the private repository's
planning documents and are not published.

## Licence

MIT; see `LICENSE`. The demo paper is made up for this project.
