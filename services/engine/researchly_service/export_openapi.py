"""Write the OpenAPI document for contract v1.

    python -m researchly_service.export_openapi            # write
    python -m researchly_service.export_openapi --check    # CI: fail on drift

Output: packages/contract/openapi.json (sorted keys, stable formatting) so a
diff shows exactly what changed in the contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .main import app

OUT = Path(__file__).resolve().parents[3] / "packages" / "contract" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"{OUT} is out of date with the service's schemas. Run:\n"
                  "  cd services/engine && python -m researchly_service.export_openapi\n"
                  "  cd packages/contract && npm run generate", file=sys.stderr)
            return 1
        print("contract up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
