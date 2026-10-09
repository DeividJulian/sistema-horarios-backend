from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Classroom, ScheduleEntry
from schemas import ClassroomCreate, ClassroomOut

router = APIRouter(prefix="/classrooms", tags=["Aulas"])


def name_in_use(db: Session, name: str, exclude_id: int | None = None) -> bool:
    query = db.query(Classroom).filter(func.lower(Classroom.nombre) == name.lower())
    if exclude_id is not None:
        query = query.filter(Classroom.id != exclude_id)
    return query.first() is not None


@router.post("", response_model=ClassroomOut)
def create_classroom(data: ClassroomCreate, db: Session = Depends(get_db)):
    if name_in_use(db, data.nombre):
        raise HTTPException(status_code=409, detail="Ya existe un aula con ese nombre")

    classroom = Classroom(**data.model_dump())
    db.add(classroom)
    db.commit()
    db.refresh(classroom)
    return classroom


@router.get("", response_model=List[ClassroomOut])
def list_classrooms(db: Session = Depends(get_db)):
    return db.query(Classroom).all()


@router.put("/{classroom_id}", response_model=ClassroomOut)
def update_classroom(classroom_id: int, data: ClassroomCreate, db: Session = Depends(get_db)):
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    if name_in_use(db, data.nombre, exclude_id=classroom_id):
        raise HTTPException(status_code=409, detail="Ya existe otra aula con ese nombre")

    classroom.nombre = data.nombre
    classroom.aforo = data.aforo
    classroom.tipo = data.tipo
    db.commit()
    db.refresh(classroom)
    return classroom


@router.delete("/{classroom_id}")
def delete_classroom(classroom_id: int, db: Session = Depends(get_db)):
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    in_use = db.query(ScheduleEntry).filter(ScheduleEntry.aula_id == classroom_id).first()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar: el aula tiene clases programadas en el horario actual.",
        )

    db.delete(classroom)
    db.commit()
    return {"mensaje": "Aula eliminada"}
