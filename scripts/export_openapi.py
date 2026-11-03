"""Writes the API contract (OpenAPI) to openapi.json, the versioned source of truth of the REST API.

    python scripts/export_openapi.py           # writes backend/openapi.json
    python scripts/export_openapi.py --check   # exits with 1 if openapi.json is out of date

The contract does not depend on the data, so the app is imported against an in-memory SQLite database:
running this script never touches the real database.
"""
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
CONTRACT = BACKEND / "openapi.json"


def contract_text(app) -> str:
    """The contract exactly as it is stored in openapi.json (stable key order, LF line endings)."""
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def stored_contract() -> str | None:
    """openapi.json as committed; Git may check it out with CRLF on Windows, so line endings are normalized."""
    return CONTRACT.read_text(encoding="utf-8").replace("\r\n", "\n") if CONTRACT.exists() else None


def render_contract() -> str:
    # Before importing the app (load_dotenv does not override variables that are already set)
    os.environ["DATABASE_URL"] = "sqlite://"
    os.environ["ADMIN_EMAIL"] = ""
    os.environ.setdefault("SECRET_KEY", "only-to-export-the-contract")
    sys.path.insert(0, str(BACKEND))
    from main import app

    return contract_text(app)


def main() -> int:
    contract = render_contract()
    if "--check" in sys.argv:
        if stored_contract() != contract:
            print("openapi.json está desactualizado: corre `python scripts/export_openapi.py`", file=sys.stderr)
            return 1
        print("openapi.json está al día")
        return 0
    CONTRACT.write_text(contract, encoding="utf-8", newline="\n")
    print(f"Contrato escrito en {CONTRACT.relative_to(BACKEND)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
