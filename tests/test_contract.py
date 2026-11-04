"""Contract-first: the versioned openapi.json must be exactly what the app generates."""
import importlib.util
from pathlib import Path

from main import app

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_openapi.py"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_versioned_contract_is_up_to_date():
    exporter = load_exporter()
    assert exporter.stored_contract() == exporter.contract_text(app), (
        "openapi.json no coincide con la API: corre `python scripts/export_openapi.py` y súbelo"
    )


def test_contract_describes_jwt_security():
    contract = app.openapi()
    assert contract["components"]["securitySchemes"]["HTTPBearer"] == {"type": "http", "scheme": "bearer"}
    assert contract["paths"]["/teachers"]["get"]["security"] == [{"HTTPBearer": []}]
    assert "security" not in contract["paths"]["/auth/login"]["post"]  # public


def test_generated_rpc_code_is_up_to_date():
    """proto/horarios/v1/horarios.proto is the RPC contract: its generated Python code must match it."""
    import subprocess
    import sys

    script = Path(__file__).resolve().parent.parent / "scripts" / "gen_proto.py"
    result = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
