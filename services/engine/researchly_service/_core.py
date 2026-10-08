"""Make `researchly` (packages/core) importable, and isolate it for hosting.

Two jobs, both done once at import:

1. **Import path.** In the Docker image `researchly` is pip-installed, so the
   import just works. In a repo checkout it is not, so this prepends
   `packages/core` to `sys.path` (equivalent to `PYTHONPATH=packages/core`).

2. **Tenant isolation.** The core was written for one person on one machine:
   `config.load()` reads `~/.researchly/config.toml` and any `.researchly.toml`
   in the working directory, and the spelling rule reads
   `~/.researchly/dictionary.txt`. In a hosted, multi-tenant service those
   files would silently apply one machine's settings to every caller's
   document. The service never calls `config.load()` (it builds a default
   `Config()` per request, see engine_adapter.py), and here the per-user file
   locations are pointed at a path that cannot exist, so nothing under HOME
   is ever read — even by code that has not been written yet.
   tests/test_isolation.py proves a planted config and dictionary have no
   effect.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_core_dir():
    """packages/core of the repo checkout this file sits in, or None (e.g.
    in the image, where the service lives at /app and has no repo above)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "packages" / "core"
        if (candidate / "researchly" / "__init__.py").exists():
            return candidate
    return None


try:                                                    # installed (Docker)
    import researchly  # noqa: F401
except ModuleNotFoundError:                             # repo checkout
    _CORE = repo_core_dir()
    if _CORE is not None:
        sys.path.insert(0, str(_CORE))
    import researchly  # noqa: F401,E402

# Health wording is truthful for where it is read (health.service_mode()).
# Set before anything asks for status.
os.environ.setdefault("RESEARCHLY_MODE", "service")

from researchly import config as _config  # noqa: E402
from researchly import gec as _gec  # noqa: E402
from researchly import spelling as _spelling  # noqa: E402

# "/dev/null/..." can never exist: /dev/null is a file, not a directory.
_NOWHERE = Path(os.devnull) / "researchly-service-reads-no-user-files"


def isolate() -> None:
    """Point every per-user file the core knows about at _NOWHERE.

    Idempotent. Called at import and again at startup (lifespan), so a test
    that re-imports core modules cannot undo it unnoticed.
    """
    _config.USER_DIR = _NOWHERE
    _config.USER_CONFIG_FILE = _NOWHERE / "config.toml"
    _spelling.USER_DICT_FILE = _NOWHERE / "dictionary.txt"
    _gec.MODEL_DIR = _NOWHERE / "models" / "gec"


isolate()

NOWHERE = _NOWHERE
