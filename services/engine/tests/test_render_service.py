"""deploy/render_service.py fills the Cloud Run spec; a bad fill is a bad deploy."""

import importlib.util
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
spec = importlib.util.spec_from_file_location("render_service", DEPLOY / "render_service.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

TEMPLATE = (DEPLOY / "cloudrun.service.yaml").read_text()
BASE = {"ENGINE_IMAGE": "img@sha256:abc", "ALLOWED_ORIGINS": "https://a.vercel.app",
        "PROJECT_ID": "p"}


def test_accounts_are_optional():
    out = rs.render(TEMPLATE, BASE)
    assert 'name: RESEARCHLY_SUPABASE_URL\n              value: ""' in out


def test_accounts_values_are_filled():
    out = rs.render(TEMPLATE, dict(BASE, SUPABASE_URL="https://abc.supabase.co",
                                   SUPABASE_PUBLISHABLE_KEY="sb_publishable_x"))
    assert 'value: "https://abc.supabase.co"' in out
    assert 'value: "sb_publishable_x"' in out
    assert "${" not in "\n".join(line for line in out.splitlines()
                                 if not line.lstrip().startswith("#"))


@pytest.mark.parametrize("bad", ['x"\n  - name: EVIL', "a\\b"])
def test_values_cannot_break_out_of_the_yaml_string(bad):
    with pytest.raises(SystemExit):
        rs.render(TEMPLATE, dict(BASE, SUPABASE_URL=bad))


def test_required_values_still_required():
    with pytest.raises(SystemExit):
        rs.render(TEMPLATE, {"ENGINE_IMAGE": "x"})
