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

# Before importing the app (load_dotenv does not override variables that are already set)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ADMIN_EMAIL"] = ""
os.environ.setdefault("SECRET_KEY", "only-to-export-the-contract")
sys.path.insert(0, str(BACKEND))


def render_contract() -> str:
    from main import app

    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    contract = render_contract()
    if "--check" in sys.argv:
        if not CONTRACT.exists() or CONTRACT.read_text(encoding="utf-8") != contract:
            print("openapi.json está desactualizado: corre `python scripts/export_openapi.py`", file=sys.stderr)
            return 1
        print("openapi.json está al día")
        return 0
    CONTRACT.write_text(contract, encoding="utf-8", newline="\n")
    print(f"Contrato escrito en {CONTRACT.relative_to(BACKEND)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
