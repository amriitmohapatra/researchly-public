# Working on Researchly

Thank you for reading the code. A few rules hold everywhere in this
repository, because they are what the product promises.

1. **No cloud models and no generative drafting.** Rules are written by hand
   and rewriting is deterministic. A learned model may only ever be a local,
   non-generative one that proposes small edits with a confidence score, and
   it is never applied automatically.
2. **Confidential by design.** Document text is processed in memory and is
   never stored, logged or used for training. The service's privacy canary
   test must stay green.
3. **Precision over recall.** A new rule needs a test where it fires and a
   test where it must not fire. Conventions are never presented as errors.
4. **Every suggestion is explainable.** A rule carries a one-line message, a
   plain explanation in everyday words, and a named source.
5. **No third-party text.** Do not paste sentences from papers, theses,
   books or course material into code, tests or fixtures. Write synthetic
   sentences, paraphrase and cite.
6. **One engine.** Every surface calls `researchly.api.analyze()`; settings
   live in `researchly/config.py`, never in a surface.

Run the checks before proposing a change:

```bash
ruff check .
cd packages/core && python -m pytest tests/ -q
cd services/engine && python -m pytest tests/ -q
cd apps/web && npm run lint && npm run typecheck && npm test
```

The engine must stay compatible with Python 3.10.

This repository is published from a private one, so a change is merged
there first and then appears here. Issues are the best way to report a
problem or suggest a check.
