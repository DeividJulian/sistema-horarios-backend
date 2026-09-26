import os
from datetime import time
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Time, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, Session, declarative_base
from pydantic import BaseModel
from typing import List

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------- MODELOS DE BASE DE DATOS ----------

class Profesor(Base):
    __tablename__ = "profesores"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)

    disponibilidades = relationship("DisponibilidadProfesor", back_populates="profesor", cascade="all, delete")


class DisponibilidadProfesor(Base):
    __tablename__ = "disponibilidad_profesor"
    id = Column(Integer, primary_key=True, index=True)
    profesor_id = Column(Integer, ForeignKey("profesores.id"), nullable=False)
    dia_semana = Column(String, nullable=False)  # Lunes, Martes, ...
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)

    profesor = relationship("Profesor", back_populates="disponibilidades")


class Aula(Base):
    __tablename__ = "aulas"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    aforo = Column(Integer, nullable=False)


class Grupo(Base):
    __tablename__ = "grupos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    num_estudiantes = Column(Integer, nullable=False)


class Materia(Base):
    __tablename__ = "materias"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    intensidad_horaria = Column(Integer, nullable=False)  # horas por semana
    grupo_id = Column(Integer, ForeignKey("grupos.id"), nullable=False)
    profesor_id = Column(Integer, ForeignKey("profesores.id"), nullable=False)

    grupo = relationship("Grupo")
    profesor = relationship("Profesor")


Base.metadata.create_all(bind=engine)

# ---------- ESQUEMAS (Pydantic) ----------

class ProfesorCreate(BaseModel):
    nombre: str
    email: str

class ProfesorOut(ProfesorCreate):
    id: int
    class Config:
        from_attributes = True


class DisponibilidadCreate(BaseModel):
    profesor_id: int
    dia_semana: str
    hora_inicio: time
    hora_fin: time

class DisponibilidadOut(DisponibilidadCreate):
    id: int
    class Config:
        from_attributes = True


class AulaCreate(BaseModel):
    nombre: str
    aforo: int

class AulaOut(AulaCreate):
    id: int
    class Config:
        from_attributes = True


class GrupoCreate(BaseModel):
    nombre: str
    num_estudiantes: int

class GrupoOut(GrupoCreate):
    id: int
    class Config:
        from_attributes = True


class MateriaCreate(BaseModel):
    nombre: str
    intensidad_horaria: int
    grupo_id: int
    profesor_id: int

class MateriaOut(MateriaCreate):
    id: int
    class Config:
        from_attributes = True


# ---------- APP ----------

app = FastAPI(title="Sistema de Horarios y Aulas Universitarias")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def root():
    return {"mensaje": "API Sistema de Horarios funcionando"}


# ---------- ENDPOINTS: PROFESORES ----------

@app.post("/profesores", response_model=ProfesorOut)
def crear_profesor(profesor: ProfesorCreate, db: Session = Depends(get_db)):
    nuevo = Profesor(**profesor.dict())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@app.get("/profesores", response_model=List[ProfesorOut])
def listar_profesores(db: Session = Depends(get_db)):
    return db.query(Profesor).all()


# ---------- ENDPOINTS: DISPONIBILIDAD ----------

@app.post("/disponibilidad", response_model=DisponibilidadOut)
def crear_disponibilidad(disp: DisponibilidadCreate, db: Session = Depends(get_db)):
    profesor = db.query(Profesor).filter(Profesor.id == disp.profesor_id).first()
    if not profesor:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")
    nueva = DisponibilidadProfesor(**disp.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

@app.get("/disponibilidad/{profesor_id}", response_model=List[DisponibilidadOut])
def listar_disponibilidad(profesor_id: int, db: Session = Depends(get_db)):
    return db.query(DisponibilidadProfesor).filter(DisponibilidadProfesor.profesor_id == profesor_id).all()


# ---------- ENDPOINTS: AULAS ----------

@app.post("/aulas", response_model=AulaOut)
def crear_aula(aula: AulaCreate, db: Session = Depends(get_db)):
    nueva = Aula(**aula.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

@app.get("/aulas", response_model=List[AulaOut])
def listar_aulas(db: Session = Depends(get_db)):
    return db.query(Aula).all()


# ---------- ENDPOINTS: GRUPOS ----------

@app.post("/grupos", response_model=GrupoOut)
def crear_grupo(grupo: GrupoCreate, db: Session = Depends(get_db)):
    nuevo = Grupo(**grupo.dict())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@app.get("/grupos", response_model=List[GrupoOut])
def listar_grupos(db: Session = Depends(get_db)):
    return db.query(Grupo).all()


# ---------- ENDPOINTS: MATERIAS ----------

@app.post("/materias", response_model=MateriaOut)
def crear_materia(materia: MateriaCreate, db: Session = Depends(get_db)):
    grupo = db.query(Grupo).filter(Grupo.id == materia.grupo_id).first()
    profesor = db.query(Profesor).filter(Profesor.id == materia.profesor_id).first()
    if not grupo or not profesor:
        raise HTTPException(status_code=404, detail="Grupo o profesor no encontrado")
    nueva = Materia(**materia.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

@app.get("/materias", response_model=List[MateriaOut])
def listar_materias(db: Session = Depends(get_db)):
    return db.query(Materia).all()