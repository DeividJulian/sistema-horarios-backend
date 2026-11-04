"""Generates the Python code of the RPC contract (proto/horarios/v1/horarios.proto).

    python scripts/gen_proto.py           # writes horarios_pb2.py, .pyi and horarios_connect.py next to the .proto
    python scripts/gen_proto.py --check   # exits with 1 if the generated code is out of date

Uses protoc from grpcio-tools and the protoc-gen-connect-python plugin (requirements-dev.txt). Do not edit the
generated files by hand.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
PROTO = "proto/horarios/v1/horarios.proto"
GENERATED = ["horarios_pb2.py", "horarios_pb2.pyi", "horarios_connect.py"]


def generate(out_dir: Path) -> None:
    env = dict(os.environ)
    # The connect plugin is installed next to the interpreter (venv/Scripts or venv/bin)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    subprocess.run(
        [
            sys.executable, "-m", "grpc_tools.protoc",
            "-I", ".",
            f"--python_out={out_dir}",
            f"--pyi_out={out_dir}",
            f"--connect-python_out={out_dir}",
            PROTO,
        ],
        cwd=BACKEND, env=env, check=True,
    )


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def main() -> int:
    target = BACKEND / Path(PROTO).parent
    if "--check" in sys.argv:
        with tempfile.TemporaryDirectory() as temp:
            generate(Path(temp))
            fresh = Path(temp) / Path(PROTO).parent
            stale = [n for n in GENERATED if not (target / n).exists() or read(target / n) != read(fresh / n)]
        if stale:
            print("Código generado desactualizado: " + ", ".join(stale) + ". Corre `python scripts/gen_proto.py`.", file=sys.stderr)
            return 1
        print("El código generado del .proto está al día")
        return 0
    with tempfile.TemporaryDirectory() as temp:
        generate(Path(temp))
        for name in GENERATED:
            shutil.copyfile(Path(temp) / Path(PROTO).parent / name, target / name)
    print("Código generado en " + str(Path(PROTO).parent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
