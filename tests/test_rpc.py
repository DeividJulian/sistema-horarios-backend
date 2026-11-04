"""RPC service (proto/horarios/v1/horarios.proto): success, errors, authentication and roles.

The Connect protocol (what the browser uses) is tested in-process; real gRPC over HTTP/2 is tested against a local
Hypercorn server with the generated client.
"""
import asyncio
import json
import socket
import struct
import threading
import time

import pytest
from fastapi.testclient import TestClient

from database import SessionLocal
from main import app
from models import ScheduleEntry, User
from proto.horarios.v1 import horarios_pb2 as pb
from security import create_token
from tests.conftest import ADMIN, READER, STUDENT, place_student

BASE = "/rpc/horarios.v1.ScheduleService"


def token_of(email: str) -> str:
    with SessionLocal() as db:
        return create_token(db.query(User).filter(User.email == email).one())


def unary(token: str | None):
    headers = {"Content-Type": "application/proto"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return TestClient(app).post(f"{BASE}/ListSchedule", content=pb.ListScheduleRequest().SerializeToString(), headers=headers)


def stream(token: str | None):
    """Server-streaming call with the Connect protocol: returns (events, end-of-stream JSON)."""
    message = pb.GenerateScheduleRequest().SerializeToString()
    headers = {"Content-Type": "application/connect+proto", "Connect-Protocol-Version": "1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = TestClient(app).post(f"{BASE}/GenerateSchedule", content=struct.pack(">BI", 0, len(message)) + message, headers=headers)
    assert response.status_code == 200, response.text
    data, events, end = response.content, [], None
    while data:
        flags, size = struct.unpack(">BI", data[:5])
        body, data = data[5 : 5 + size], data[5 + size :]
        if flags & 0x02:
            end = json.loads(body or b"{}")
        else:
            events.append(pb.GenerationEvent.FromString(body))
    return events, end


@pytest.fixture
def faculty(client):
    assert client.post("/seed?dataset=faculty").status_code == 200
    return client


def test_list_schedule_returns_the_same_data_as_rest(faculty):
    faculty.post("/schedules/generate")
    rest = faculty.get("/schedules").json()
    response = unary(token_of(ADMIN["email"]))
    assert response.status_code == 200 and response.headers["content-type"] == "application/proto"
    entries = pb.ListScheduleResponse.FromString(response.content).entries
    assert len(entries) == len(rest) > 0
    first = next(e for e in entries if e.id == rest[0]["id"])
    assert first.subject_id == rest[0]["materia_id"] and first.classroom_id == rest[0]["aula_id"]
    assert pb.Weekday.Name(first.weekday) == "WEEKDAY_" + rest[0]["dia_semana"].upper().replace("É", "E")
    assert first.start_hour == int(rest[0]["hora_inicio"][:2])
    # Protobuf is smaller than the JSON of the same data
    assert len(response.content) < len(json.dumps(rest).encode())


def test_a_student_only_gets_their_group(faculty):
    faculty.post("/schedules/generate")
    place_student(faculty)
    entries = pb.ListScheduleResponse.FromString(unary(token_of(STUDENT["email"])).content).entries
    with SessionLocal() as db:
        student = db.query(User).filter(User.email == STUDENT["email"]).one()
        of_group = {e.id for e in db.query(ScheduleEntry).all() if e.subject.grupo_id == student.grupo_id}
        everything = db.query(ScheduleEntry).count()
    assert {e.id for e in entries} == of_group and 0 < len(entries) < everything


def test_generation_streams_every_phase_and_saves_the_schedule(faculty):
    events, end = stream(token_of(ADMIN["email"]))
    assert end == {}
    phases = [pb.Phase.Name(e.phase) for e in events]
    for phase in ("PHASE_PREPARING", "PHASE_CSP", "PHASE_ANNEALING", "PHASE_SAVING", "PHASE_DONE"):
        assert phase in phases, phases
    assert phases.index("PHASE_CSP") < phases.index("PHASE_ANNEALING") < phases.index("PHASE_DONE")
    csp = [e for e in events if e.phase == pb.PHASE_CSP]
    assert csp[-1].subjects_placed == csp[-1].total_subjects > 0
    done = events[-1]
    assert done.phase == pb.PHASE_DONE and done.total_blocks == len(faculty.get("/schedules").json()) > 0
    assert done.idle_hours <= done.idle_hours_before
    assert all(e.message for e in events)


def test_without_token_or_with_a_bad_one_it_is_unauthenticated(faculty):
    for token in (None, "no-es-un-token", create_token(User(id=999, rol="admin"))):
        response = unary(token)
        assert response.status_code == 401 and response.json()["code"] == "unauthenticated"
    events, end = stream(None)
    assert events == [] and end["error"]["code"] == "unauthenticated"


def test_only_administrators_generate(faculty, reader_client):
    events, end = stream(token_of(READER["email"]))
    assert events == [] and end["error"]["code"] == "permission_denied"
    assert "administrador" in end["error"]["message"]
    assert unary(token_of(READER["email"])).status_code == 200  # reading is allowed, as in REST


def test_an_impossible_schedule_ends_the_stream_with_a_clear_error(client):
    client.post("/classrooms", json={"nombre": "Aula", "aforo": 30})
    group = client.post("/groups", json={"nombre": "Grupo único", "num_estudiantes": 20}).json()
    teacher = client.post("/teachers", json={"nombre": "Sin Horas", "email": "sin@ucc.edu.co"}).json()
    client.post("/subjects", json={"nombre": "Materia", "intensidad_horaria": 3, "grupo_id": group["id"], "profesor_id": teacher["id"]})
    events, end = stream(token_of(ADMIN["email"]))
    assert end["error"]["code"] == "failed_precondition" and end["error"]["message"]
    assert all(e.phase != pb.PHASE_DONE for e in events)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def grpc_server():
    """The same app served by Hypercorn with HTTP/2 (h2c), as a gRPC server would be."""
    hypercorn = pytest.importorskip("hypercorn.asyncio")
    from hypercorn.config import Config

    config = Config()
    port = free_port()
    config.bind = [f"127.0.0.1:{port}"]
    config.loglevel = "WARNING"
    stop = asyncio.Event()
    loop = asyncio.new_event_loop()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(hypercorn.serve(app, config, shutdown_trigger=stop.wait))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    for _ in range(100):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/rpc"
    loop.call_soon_threadsafe(stop.set)
    thread.join(timeout=5)


def test_real_grpc_over_http2_with_the_generated_client(faculty, grpc_server):
    from connectrpc.errors import ConnectError
    from connectrpc.protocol import ProtocolType
    from pyqwest import Client, HTTPTransport, HTTPVersion

    from proto.horarios.v1.horarios_connect import ScheduleServiceClient

    async def call():
        token = {"authorization": f"Bearer {token_of(ADMIN['email'])}"}
        # gRPC needs HTTP/2 (its status travels in trailers): plaintext HTTP/2 with prior knowledge, like grpc clients
        http2 = Client(HTTPTransport(http_version=HTTPVersion.HTTP2))
        async with ScheduleServiceClient(grpc_server, protocol=ProtocolType.GRPC, http_client=http2) as client:
            phases = [e.phase async for e in client.generate_schedule(pb.GenerateScheduleRequest(), headers=token)]
            listed = await client.list_schedule(pb.ListScheduleRequest(), headers=token)
            with pytest.raises(ConnectError) as denied:
                await client.list_schedule(pb.ListScheduleRequest())
        return phases, listed, denied.value

    phases, listed, denied = asyncio.run(call())
    assert phases[-1] == pb.PHASE_DONE and pb.PHASE_CSP in phases
    assert len(listed.entries) == len(faculty.get("/schedules").json()) > 0
    assert denied.code.name == "UNAUTHENTICATED"
