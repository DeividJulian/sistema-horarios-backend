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
    dia_semana = Column(String, nullable=False)
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
    intensidad_horaria = Column(Integer, nullable=False)
    grupo_id = Column(Integer, ForeignKey("grupos.id"), nullable=False)
    profesor_id = Column(Integer, ForeignKey("profesores.id"), nullable=False)

    grupo = relationship("Grupo")
    profesor = relationship("Profesor")


class Horario(Base):
    __tablename__ = "horarios"
    id = Column(Integer, primary_key=True, index=True)
    materia_id = Column(Integer, ForeignKey("materias.id"), nullable=False)
    aula_id = Column(Integer, ForeignKey("aulas.id"), nullable=False)
    dia_semana = Column(String, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)

    materia = relationship("Materia")
    aula = relationship("Aula")


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


class HorarioOut(BaseModel):
    id: int
    materia_id: int
    aula_id: int
    dia_semana: str
    hora_inicio: time
    hora_fin: time
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


# ---------- ALGORITMO CSP: ASIGNACIÓN DE HORARIOS ----------

def generar_bloques_horarios(hora_inicio: time, hora_fin: time):
    """Convierte un rango de disponibilidad en bloques de 1 hora."""
    bloques = []
    h = hora_inicio.hour
    while h < hora_fin.hour:
        bloques.append(time(hour=h))
        h += 1
    return bloques


def calcular_asignaciones(db: Session):
    materias = db.query(Materia).all()
    aulas = db.query(Aula).all()
    grupos = {g.id: g for g in db.query(Grupo).all()}

    if not materias or not aulas:
        return False, [], "No hay materias o aulas registradas."

    # Disponibilidad de cada profesor como conjunto de (dia, hora)
    disponibilidad_por_profesor = {}
    for materia in materias:
        pid = materia.profesor_id
        if pid not in disponibilidad_por_profesor:
            slots = set()
            disponibilidades = db.query(DisponibilidadProfesor).filter(
                DisponibilidadProfesor.profesor_id == pid
            ).all()
            for d in disponibilidades:
                for h in generar_bloques_horarios(d.hora_inicio, d.hora_fin):
                    slots.add((d.dia_semana, h))
            disponibilidad_por_profesor[pid] = slots

    # Ordenar: materias cuyo profesor tiene MENOS disponibilidad van primero (más restringido primero)
    materias_ordenadas = sorted(
        materias,
        key=lambda m: len(disponibilidad_por_profesor.get(m.profesor_id, set()))
    )

    ocupado_profesor = set()
    ocupado_aula = set()
    ocupado_grupo = set()
    resultado_final = []

    def backtrack(index):
        if index == len(materias_ordenadas):
            return True

        materia = materias_ordenadas[index]
        grupo = grupos.get(materia.grupo_id)
        if grupo is None:
            return False

        slots_profesor = disponibilidad_por_profesor.get(materia.profesor_id, set())
        aulas_validas = [a for a in aulas if a.aforo >= grupo.num_estudiantes]

        candidatos = [(dia, hora, aula) for (dia, hora) in slots_profesor for aula in aulas_validas]

        asignaciones_materia = []

        def backtrack_bloques(pos, dias_usados):
            if pos == materia.intensidad_horaria:
                return True
            for (dia, hora, aula) in candidatos:
                if dia in dias_usados:
                    continue
                clave_prof = (materia.profesor_id, dia, hora)
                clave_aula = (aula.id, dia, hora)
                clave_grupo = (materia.grupo_id, dia, hora)
                if clave_prof in ocupado_profesor or clave_aula in ocupado_aula or clave_grupo in ocupado_grupo:
                    continue

                ocupado_profesor.add(clave_prof)
                ocupado_aula.add(clave_aula)
                ocupado_grupo.add(clave_grupo)
                asignaciones_materia.append((materia, aula, dia, hora))
                dias_usados.add(dia)

                if backtrack_bloques(pos + 1, dias_usados):
                    return True

                ocupado_profesor.discard(clave_prof)
                ocupado_aula.discard(clave_aula)
                ocupado_grupo.discard(clave_grupo)
                asignaciones_materia.pop()
                dias_usados.discard(dia)
            return False

        if not backtrack_bloques(0, set()):
            return False

        resultado_final.extend(asignaciones_materia)

        if backtrack(index + 1):
            return True

        # Deshacer si una materia posterior no tiene solución
        for (m, aula, dia, hora) in asignaciones_materia:
            ocupado_profesor.discard((m.profesor_id, dia, hora))
            ocupado_aula.discard((aula.id, dia, hora))
            ocupado_grupo.discard((m.grupo_id, dia, hora))
            resultado_final.remove((m, aula, dia, hora))
        return False

    exito = backtrack(0)

    if not exito:
        return False, [], "No fue posible generar un horario sin cruces con los datos actuales. Revisa disponibilidad de profesores o número de aulas disponibles."

    return True, resultado_final, "OK"


@app.post("/generar-horario", response_model=List[HorarioOut])
def generar_horario(db: Session = Depends(get_db)):
    exito, asignaciones, mensaje = calcular_asignaciones(db)
    if not exito:
        raise HTTPException(status_code=409, detail=mensaje)

    db.query(Horario).delete()
    db.commit()

    for (materia, aula, dia, hora) in asignaciones:
        nueva_hora_fin = time(hour=hora.hour + 1)
        nuevo_horario = Horario(
            materia_id=materia.id,
            aula_id=aula.id,
            dia_semana=dia,
            hora_inicio=hora,
            hora_fin=nueva_hora_fin,
        )
        db.add(nuevo_horario)
    db.commit()

    return db.query(Horario).all()


@app.get("/horarios", response_model=List[HorarioOut])
def listar_horarios(db: Session = Depends(get_db)):
    return db.query(Horario).all()


@app.get("/horarios/grupo/{grupo_id}", response_model=List[HorarioOut])
def listar_horarios_por_grupo(grupo_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Horario)
        .join(Materia, Horario.materia_id == Materia.id)
        .filter(Materia.grupo_id == grupo_id)
        .all()
    )