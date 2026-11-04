"""RPC service (Connect / gRPC) of proto/horarios/v1/horarios.proto, mounted in the FastAPI app under /rpc.

It reuses the same logic as REST (services/generation.py) and the same sessions and roles (security.user_from_token):
the JWT travels in the `Authorization: Bearer <token>` header, which in Connect and gRPC is request metadata.
"""
import asyncio
import logging
import threading
import time as clock

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext

from database import SessionLocal
from models import User
from proto.horarios.v1 import horarios_pb2 as pb
from proto.horarios.v1.horarios_connect import ScheduleServiceASGIApplication
from security import user_from_token
from services.generation import GenerationFailed, generate_and_save, schedule_for

logger = logging.getLogger("schedule.rpc")

WEEKDAYS = {
    "Lunes": pb.WEEKDAY_LUNES,
    "Martes": pb.WEEKDAY_MARTES,
    "Miércoles": pb.WEEKDAY_MIERCOLES,
    "Jueves": pb.WEEKDAY_JUEVES,
    "Viernes": pb.WEEKDAY_VIERNES,
}
# Progress events closer than this are skipped (the first and last of each phase always go out)
MIN_EVENT_GAP_SECONDS = 0.05

_END = object()


class GenerationCancelled(Exception):
    """The client cancelled the stream: the generation stops before saving anything."""


def authenticate(ctx: RequestContext) -> User:
    """Same rules as the REST endpoints: a valid token of a verified account, read from the request metadata."""
    header = ctx.request_headers().get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ConnectError(Code.UNAUTHENTICATED, "Debes iniciar sesión.")
    with SessionLocal() as db:
        user = user_from_token(db, token)
        if user is None:
            raise ConnectError(Code.UNAUTHENTICATED, "Tu sesión no es válida o expiró. Inicia sesión de nuevo.")
        db.expunge(user)
        return user


def to_message(entry) -> pb.ScheduleEntry:
    return pb.ScheduleEntry(
        id=entry.id,
        subject_id=entry.materia_id,
        classroom_id=entry.aula_id,
        weekday=WEEKDAYS.get(entry.dia_semana, pb.WEEKDAY_UNSPECIFIED),
        start_hour=entry.hora_inicio.hour,
        end_hour=entry.hora_fin.hour,
    )


class ScheduleRpc:
    """Implements ScheduleService (see the generated horarios_connect.py)."""

    async def list_schedule(self, request: pb.ListScheduleRequest, ctx: RequestContext) -> pb.ListScheduleResponse:
        user = authenticate(ctx)
        with SessionLocal() as db:
            return pb.ListScheduleResponse(entries=[to_message(e) for e in schedule_for(db, user)])

    async def generate_schedule(self, request: pb.GenerateScheduleRequest, ctx: RequestContext):
        user = authenticate(ctx)
        if user.rol != "admin":
            raise ConnectError(Code.PERMISSION_DENIED, "Solo un administrador puede generar el horario.")

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        cancelled = threading.Event()
        started = clock.perf_counter()
        last_sent = {"phase": None, "at": 0.0}

        def emit(item) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, item)

        def progress(phase: str, **figures) -> None:
            # Runs in the worker thread, inside the CSP and the annealing
            if cancelled.is_set():
                raise GenerationCancelled()
            now = clock.perf_counter()
            event = pb.GenerationEvent(elapsed_seconds=round(now - started, 3))
            if phase == "preparing":
                event.phase = pb.PHASE_PREPARING
                event.total_subjects = figures["subjects"]
                event.message = f"Preparando {figures['subjects']} materias y {figures['classrooms']} aulas"
            elif phase == "csp":
                event.phase = pb.PHASE_CSP
                event.subjects_placed, event.total_subjects = figures["placed"], figures["total"]
                event.message = f"CSP: {figures['placed']} de {figures['total']} materias sin cruces"
            elif phase == "annealing":
                event.phase = pb.PHASE_ANNEALING
                event.iterations, event.improvements = figures["iterations"], figures["improvements"]
                event.idle_hours, event.idle_hours_before = figures["idle"], figures["idle_before"]
                event.message = f"Recocido simulado: {figures['idle']} horas muertas (antes {figures['idle_before']})"
            elif phase == "saving":
                event.phase = pb.PHASE_SAVING
                event.total_blocks = figures["blocks"]
                event.message = f"Guardando {figures['blocks']} bloques"
            new_phase = event.phase != last_sent["phase"]
            done_csp = phase == "csp" and figures["placed"] == figures["total"]
            if new_phase or done_csp or now - last_sent["at"] >= MIN_EVENT_GAP_SECONDS:
                last_sent.update(phase=event.phase, at=now)
                emit(event)

        def work() -> None:
            try:
                with SessionLocal() as db:
                    total, optimization = generate_and_save(db, progress=progress)
                emit(
                    pb.GenerationEvent(
                        phase=pb.PHASE_DONE,
                        message="Horario generado exitosamente",
                        total_blocks=total,
                        idle_hours=optimization.get("horas_muertas_despues", 0),
                        idle_hours_before=optimization.get("horas_muertas_antes", 0),
                        iterations=optimization.get("iteraciones", 0),
                        improvements=optimization.get("mejoras", 0),
                        elapsed_seconds=round(clock.perf_counter() - started, 3),
                    )
                )
            except GenerationCancelled:
                logger.info("Generation cancelled by the client: nothing was saved")
            except GenerationFailed as e:
                emit(ConnectError(Code.FAILED_PRECONDITION, str(e)))
            except Exception as e:  # never leak internals to the client
                logger.error("RPC generation failed", exc_info=e)
                emit(ConnectError(Code.INTERNAL, "Error interno al generar el horario. Intenta de nuevo."))
            finally:
                emit(_END)

        worker = loop.run_in_executor(None, work)
        try:
            while True:
                item = await queue.get()
                if item is _END:
                    break
                if isinstance(item, ConnectError):
                    raise item
                yield item
        finally:
            # The client went away (or the stream ended): a worker still running stops at its next progress report,
            # before saving anything
            cancelled.set()


def create_rpc_app() -> ScheduleServiceASGIApplication:
    return ScheduleServiceASGIApplication(ScheduleRpc())
