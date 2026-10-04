from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Classroom, ScheduleEntry
from schemas import ClassroomCreate, ClassroomOut

router = APIRouter(prefix="/aulas", tags=["Aulas"])


def nombre_en_uso(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    consulta = db.query(Classroom).filter(func.lower(Classroom.nombre) == nombre.lower())
    if excluir_id is not None:
        consulta = consulta.filter(Classroom.id != excluir_id)
    return consulta.first() is not None


@router.post("", response_model=ClassroomOut)
def crear_aula(classroom: ClassroomCreate, db: Session = Depends(get_db)):
    if nombre_en_uso(db, classroom.nombre):
        raise HTTPException(status_code=409, detail="Ya existe un aula con ese nombre")

    nueva = Classroom(**classroom.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.get("", response_model=List[ClassroomOut])
def listar_aulas(db: Session = Depends(get_db)):
    return db.query(Classroom).all()


@router.put("/{aula_id}", response_model=ClassroomOut)
def actualizar_aula(aula_id: int, datos: ClassroomCreate, db: Session = Depends(get_db)):
    classroom = db.query(Classroom).filter(Classroom.id == aula_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    if nombre_en_uso(db, datos.nombre, excluir_id=aula_id):
        raise HTTPException(status_code=409, detail="Ya existe otra aula con ese nombre")

    classroom.nombre = datos.nombre
    classroom.aforo = datos.aforo
    db.commit()
    db.refresh(classroom)
    return classroom


@router.delete("/{aula_id}")
def eliminar_aula(aula_id: int, db: Session = Depends(get_db)):
    classroom = db.query(Classroom).filter(Classroom.id == aula_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    en_uso = db.query(ScheduleEntry).filter(ScheduleEntry.aula_id == aula_id).first()
    if en_uso:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar: el aula tiene clases programadas en el horario actual.",
        )

    db.delete(classroom)
    db.commit()
    return {"mensaje": "Aula eliminada"}
