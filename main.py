import logging
import time

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import models  # noqa: F401  (registers the tables on Base)
from database import Base, SessionLocal, engine, get_db
from migrations import apply_migrations
from routers import ai, analysis, auth, availability, class_changes, classrooms, groups, schedules, seed, subjects, teachers, users
from schemas import ErrorOut, HealthOut, RootOut
from security import authorize
from services.users import ensure_admin, sync_accounts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("schedule.api")

Base.metadata.create_all(bind=engine)
apply_migrations(engine)
with SessionLocal() as session:
    ensure_admin(session)  # first administrator from ADMIN_EMAIL
    sync_accounts(session)  # one account per teacher

# Error codes each group of routes can answer, all with the shape {"detail": "text"} (see the handlers below)
ERROR_TEXT = {
    400: "Solicitud incorrecta (por ejemplo, un código de verificación inválido o vencido)",
    401: "Sin sesión, o token inválido o vencido",
    403: "El rol del usuario no permite esta acción",
    404: "El recurso no existe",
    409: "Conflicto con los datos actuales (duplicado, cruce de horario, etc.)",
    422: "Datos de entrada inválidos",
    429: "Demasiadas solicitudes (espera entre códigos o límite de la IA)",
    500: "Error interno de la base de datos",
    502: "Falló un servicio externo (correo o IA)",
    503: "La IA no está configurada en el servidor",
}


def errors(*codes: int) -> dict:
    return {code: {"model": ErrorOut, "description": ERROR_TEXT[code]} for code in codes}


app = FastAPI(
    responses=errors(500),
    title="Sistema de Horarios y Aulas Universitarias",
    version="2.0.0",
    description=(
        "API REST del sistema de horarios. El contrato versionado vive en openapi.json "
        "(se regenera con scripts/export_openapi.py). Autenticación: token JWT en la cabecera "
        "Authorization: Bearer <token>, obtenido con POST /auth/verify."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public: sign-up and login with a code sent by email. Users: administrators only.
app.include_router(auth.router, responses=errors(400, 401, 404, 409, 422, 429, 502))
app.include_router(users.router, responses=errors(401, 403, 404, 409, 422))
# Teachers cancel their classes or change the classroom; students read their notices
app.include_router(class_changes.router, responses=errors(401, 403, 404, 409, 422))
# The AI advises (conflicts, notices); it never changes data by itself
app.include_router(ai.router, responses=errors(401, 403, 404, 422, 429, 502, 503))

# Data: every signed-in user can read, only administrators can create, edit, delete or generate
for data_router in (teachers, availability, classrooms, groups, subjects, schedules, analysis, seed):
    app.include_router(data_router.router, dependencies=[Depends(authorize)], responses=errors(401, 403, 404, 409, 422))


# ---------- LOGGING: every request is logged with method, path, status code and duration ----------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - started) * 1000
    logger.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, ms)
    return response


# ---------- UNIFORM ERROR HANDLING: every error response has the shape {"detail": "text"} ----------

@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    messages = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"] if part != "body")
        message = error["msg"].removeprefix("Value error, ")
        messages.append(f"{field}: {message}" if field else message)
    logger.warning("Validation failed on %s %s: %s", request.method, request.url.path, messages)
    return JSONResponse(status_code=422, content={"detail": "; ".join(messages)})


@app.exception_handler(IntegrityError)
async def handle_integrity_error(request: Request, exc: IntegrityError):
    logger.warning("Integrity violation on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=409,
        content={"detail": "La operacion viola una restriccion de la base de datos (dato duplicado o referencia inexistente)."},
    )


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(request: Request, exc: SQLAlchemyError):
    logger.error("Database error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno de la base de datos. Intenta de nuevo."},
    )


@app.get("/", response_model=RootOut)
def root():
    return {"mensaje": "API Sistema de Horarios funcionando"}


@app.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"estado": "ok", "base_de_datos": "conectada"}
