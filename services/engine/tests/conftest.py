"""Shared fixtures for the engine-service tests.

Run from services/engine:  python -m pytest tests/ -q -p no:cacheprovider

`researchly` (packages/core) is found by researchly_service/_core.py, so no
PYTHONPATH is needed in a repo checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))           # researchly_service

from fastapi.testclient import TestClient  # noqa: E402

from researchly_service import settings as settings_mod  # noqa: E402
from researchly_service.main import create_app  # noqa: E402

# Synthetic test prose only — never thesis or course text (CLAUDE.md).
PASSIVE = "The model was calibrated by the authors using weekly data."
METHODS_PASSIVE = "Methods\n\n" + PASSIVE
DISCUSSION_PASSIVE = "Discussion\n\n" + PASSIVE
PREFERENCE_TEXT = "Results\n\nThe effect was very large in every district."


def make_settings(**kw) -> settings_mod.Settings:
    base = dict(env="production", allowed_origins=[], grammar_enabled=True,
                max_body_bytes=4 * 1024 * 1024, rate_limit_per_min=0,
                trusted_proxy_hops=0, warmup=True)
    base.update(kw)
    return settings_mod.Settings(**base)


@pytest.fixture
def make_client():
    """Factory: a TestClient (lifespan entered) for custom settings."""
    opened = []

    def _make(**kw) -> TestClient:
        c = TestClient(create_app(make_settings(**kw)),
                       raise_server_exceptions=False)
        c.__enter__()
        opened.append(c)
        return c
    yield _make
    for c in opened:
        c.__exit__(None, None, None)


@pytest.fixture(scope="module")
def client():
    """Default client: production settings, no rate limit, warm engine."""
    with TestClient(create_app(make_settings()),
                    raise_server_exceptions=False) as c:
        yield c


def analyze(client, content, fmt="plain", **options):
    body = {"format": fmt, "content": content}
    if options:
        body["options"] = options
    return client.post("/v1/analyze", json=body)


def rule_ids(resp) -> set:
    return {s["rule_id"] for s in resp.json()["suggestions"]}
