from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Teacher, TeacherAvailability
from schemas import AvailabilityCreate, AvailabilityOut

router = APIRouter(prefix="/availability", tags=["Disponibilidad"])


@router.post("", response_model=AvailabilityOut)
def create_availability(data: AvailabilityCreate, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == data.profesor_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")
    availability = TeacherAvailability(**data.model_dump())
    db.add(availability)
    db.commit()
    db.refresh(availability)
    return availability


@router.get("/{teacher_id}", response_model=List[AvailabilityOut])
def list_availability(teacher_id: int, db: Session = Depends(get_db)):
    return (
        db.query(TeacherAvailability)
        .filter(TeacherAvailability.profesor_id == teacher_id)
        .all()
    )


@router.delete("/{availability_id}")
def delete_availability(availability_id: int, db: Session = Depends(get_db)):
    availability = (
        db.query(TeacherAvailability)
        .filter(TeacherAvailability.id == availability_id)
        .first()
    )
    if not availability:
        raise HTTPException(status_code=404, detail="Disponibilidad no encontrada")

    db.delete(availability)
    db.commit()
    return {"mensaje": "Disponibilidad eliminada"}
