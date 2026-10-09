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
from routers import analysis, auth, availability, classrooms, groups, schedules, seed, subjects, teachers, users
from security import authorize
from services.users import ensure_default_users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("schedule.api")

Base.metadata.create_all(bind=engine)
apply_migrations(engine)
with SessionLocal() as session:
    ensure_default_users(session)

app = FastAPI(title="Sistema de Horarios y Aulas Universitarias")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public: login. Users: administrators only.
app.include_router(auth.router)
app.include_router(users.router)

# Data: every signed-in user can read, only administrators can create, edit, delete or generate
for data_router in (teachers, availability, classrooms, groups, subjects, schedules, analysis, seed):
    app.include_router(data_router.router, dependencies=[Depends(authorize)])


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


@app.get("/")
def root():
    return {"mensaje": "API Sistema de Horarios funcionando"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"estado": "ok", "base_de_datos": "conectada"}
