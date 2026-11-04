"""REST (JSON) vs gRPC (Protobuf) with the same data: size of the message and time to encode and decode it.

    python scripts/benchmark_protocols.py

Loads the 8-semester faculty into an in-memory SQLite database (never the real one), generates the schedule and
measures the GET /schedules answer (JSON, same serializer as the API) against ListSchedule (Protobuf), for the real
schedule and for a 10x larger one (a whole university). The network is not measured here: the browser comparison in
Análisis does that against the real server.
"""
import gzip
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ADMIN_EMAIL"] = ""
os.environ.setdefault("SECRET_KEY", "only-for-the-benchmark")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal  # noqa: E402
from main import app  # noqa: E402,F401  (creates the tables)
from models import ScheduleEntry  # noqa: E402
from proto.horarios.v1 import horarios_pb2 as pb  # noqa: E402
from schemas import ScheduleEntryOut  # noqa: E402
from services.generation import generate_and_save  # noqa: E402
from services.rpc import to_message  # noqa: E402
from services.seed import load_faculty_data  # noqa: E402

REPEAT = 300


def timed(function) -> float:
    """Median time of one call, in microseconds."""
    samples = []
    for _ in range(REPEAT):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1e6)
    return statistics.median(samples)


def measure(entries) -> dict:
    rows = [ScheduleEntryOut.model_validate(e).model_dump(mode="json") for e in entries]
    as_json = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    message = pb.ListScheduleResponse(entries=[to_message(e) for e in entries])
    as_proto = message.SerializeToString()
    return {
        "bloques": len(entries),
        "json_bytes": len(as_json),
        "proto_bytes": len(as_proto),
        "json_gzip": len(gzip.compress(as_json)),
        "proto_gzip": len(gzip.compress(as_proto)),
        "json_encode_us": timed(lambda: json.dumps(rows, separators=(",", ":")).encode()),
        "proto_encode_us": timed(message.SerializeToString),
        "json_decode_us": timed(lambda: json.loads(as_json)),
        "proto_decode_us": timed(lambda: pb.ListScheduleResponse.FromString(as_proto)),
    }


def main() -> None:
    with SessionLocal() as db:
        load_faculty_data(db)
        generate_and_save(db)
        entries = db.query(ScheduleEntry).all()
        # A whole university: the same week repeated with other ids
        big = []
        for copy in range(10):
            for e in entries:
                big.append(ScheduleEntry(id=e.id + copy * 100000, materia_id=e.materia_id + copy * 1000, aula_id=e.aula_id,
                                         dia_semana=e.dia_semana, hora_inicio=e.hora_inicio, hora_fin=e.hora_fin))
        results = [measure(entries), measure(big)]

    print("| Medida | " + " | ".join(f"{r['bloques']} bloques" for r in results) + " |")
    print("|---|" + "---|" * len(results))
    rows = [
        ("JSON (REST)", "json_bytes", "B"), ("Protobuf (gRPC)", "proto_bytes", "B"),
        ("JSON con gzip", "json_gzip", "B"), ("Protobuf con gzip", "proto_gzip", "B"),
        ("Codificar JSON", "json_encode_us", "µs"), ("Codificar Protobuf", "proto_encode_us", "µs"),
        ("Decodificar JSON", "json_decode_us", "µs"), ("Decodificar Protobuf", "proto_decode_us", "µs"),
    ]
    for label, key, unit in rows:
        print(f"| {label} | " + " | ".join(f"{r[key]:,.0f} {unit}".replace(",", ".") for r in results) + " |")
    for r in results:
        print(f"\n{r['bloques']} bloques: Protobuf ocupa {r['json_bytes'] / r['proto_bytes']:.1f}x menos que JSON "
              f"({r['json_gzip'] / r['proto_gzip']:.1f}x menos con gzip)")


if __name__ == "__main__":
    main()
