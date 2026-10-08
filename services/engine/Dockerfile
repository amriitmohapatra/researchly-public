# syntax=docker/dockerfile:1.7
#
# Researchly engine service image (ARCHITECTURE.md §5.2, ADR-03).
#
# Build from the REPO ROOT (the context is the repo, filtered by the
# allow-list in /.dockerignore):
#
#     docker build -f services/engine/Dockerfile -t researchly-engine .
#
# Privacy control (§9 "Repo hygiene"): only packages/core/researchly,
# packages/core/requirements.txt and the service itself are copied. Never
# Sample_thesis_drafts/, Notes_On_Writing/, ml/ or legacy/ — the
# .dockerignore keeps them out of the build context entirely, and the COPY
# lines below name exact paths as a second fence.
#
# No Java here: LanguageTool runs as a sidecar container (docker-compose.yml,
# deploy/cloudrun.service.yaml) reached via RESEARCHLY_LT_URL.
#
# Behind a TLS-intercepting proxy (corporate networks, some CI sandboxes),
# pass its CA without baking it into a layer:
#     docker build --secret id=extra_ca,src=/path/to/ca.crt ...

FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first (their own layer, cached until a requirements file
# changes). The core's floors are applied as constraints: its pytest/pygls
# dev entries are therefore never installed.
COPY packages/core/requirements.txt /tmp/core-requirements.txt
COPY services/engine/requirements.txt /tmp/service-requirements.txt
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then \
        cat /etc/ssl/certs/ca-certificates.crt /run/secrets/extra_ca > /tmp/ca.pem; \
        export PIP_CERT=/tmp/ca.pem; \
    fi; \
    pip install -r /tmp/service-requirements.txt -c /tmp/core-requirements.txt \
    && rm -f /tmp/ca.pem /tmp/*-requirements.txt

# The engine package, installed onto the import path with a .pth file (the
# core has no packaging metadata yet; this is equivalent to an editable
# install of exactly one directory).
COPY packages/core/researchly /opt/researchly/core/researchly
RUN python -c "import site; open(site.getsitepackages()[0] + '/researchly-core.pth', 'w').write('/opt/researchly/core\n')"

COPY services/engine/researchly_service /app/researchly_service

# Non-root, with an empty HOME: the service reads no per-user files anyway
# (researchly_service/_core.py), and there are none to read.
RUN useradd --uid 10001 --create-home --home-dir /home/researchly researchly \
    && python -c "import researchly, researchly_service.main, spacy; spacy.load('en_core_web_sm')"
USER 10001

ENV RESEARCHLY_MODE=service \
    RESEARCHLY_ENV=production \
    PORT=8080

EXPOSE 8080

# Cloud Run sends SIGTERM and sets $PORT; uvicorn opens the port only after
# the lifespan warm-up, so the startup probe passes on a warm engine.
CMD ["python", "-m", "researchly_service"]
