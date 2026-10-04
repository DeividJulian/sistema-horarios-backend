from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
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


@app.get("/")
def root():
    return {"mensaje": "API Sistema de Horarios funcionando"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"estado": "ok", "base_de_datos": "conectada"}
