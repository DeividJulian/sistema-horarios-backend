from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ScheduleEntry, StudentGroup, Subject, Teacher
from schemas import SubjectCreate, SubjectOut

router = APIRouter(prefix="/subjects", tags=["Materias"])


def validate_references(data: SubjectCreate, db: Session):
    group = db.query(StudentGroup).filter(StudentGroup.id == data.grupo_id).first()
    teacher = db.query(Teacher).filter(Teacher.id == data.profesor_id).first()
    if not group or not teacher:
        raise HTTPException(status_code=404, detail="Grupo o profesor no encontrado")


@router.post("", response_model=SubjectOut)
def create_subject(data: SubjectCreate, db: Session = Depends(get_db)):
    validate_references(data, db)
    subject = Subject(**data.model_dump())
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


@router.get("", response_model=List[SubjectOut])
def list_subjects(db: Session = Depends(get_db)):
    return db.query(Subject).all()


@router.put("/{subject_id}", response_model=SubjectOut)
def update_subject(subject_id: int, data: SubjectCreate, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    validate_references(data, db)

    subject.nombre = data.nombre
    subject.intensidad_horaria = data.intensidad_horaria
    subject.grupo_id = data.grupo_id
    subject.profesor_id = data.profesor_id
    subject.tipo_aula = data.tipo_aula
    db.commit()
    db.refresh(subject)
    return subject


@router.delete("/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    # The subject's schedule blocks would be left orphaned, so they are deleted first
    db.query(ScheduleEntry).filter(ScheduleEntry.materia_id == subject_id).delete()
    db.delete(subject)
    db.commit()
    return {"mensaje": "Materia eliminada junto con sus bloques de horario"}
