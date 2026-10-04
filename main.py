from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import models  # noqa: F401  (registra las tablas en Base)
from database import Base, engine, get_db
from routers import aulas, disponibilidad, grupos, horarios, materias, profesores

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sistema de Horarios y Aulas Universitarias")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profesores.router)
app.include_router(disponibilidad.router)
app.include_router(aulas.router)
app.include_router(grupos.router)
app.include_router(materias.router)
app.include_router(horarios.router)


# ---------- MANEJO DE ERRORES UNIFORME: todas las respuestas de error tienen la forma {"detail": "texto"} ----------

@app.exception_handler(RequestValidationError)
async def manejar_validacion(request: Request, exc: RequestValidationError):
    mensajes = []
    for error in exc.errors():
        campo = ".".join(str(parte) for parte in error["loc"] if parte != "body")
        mensaje = error["msg"].removeprefix("Value error, ")
        mensajes.append(f"{campo}: {mensaje}" if campo else mensaje)
    return JSONResponse(status_code=422, content={"detail": "; ".join(mensajes)})


@app.exception_handler(IntegrityError)
async def manejar_integridad(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=409,
        content={"detail": "La operacion viola una restriccion de la base de datos (dato duplicado o referencia inexistente)."},
    )


@app.exception_handler(SQLAlchemyError)
async def manejar_error_bd(request: Request, exc: SQLAlchemyError):
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
