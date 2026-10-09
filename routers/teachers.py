from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Subject, Teacher
from schemas import TeacherCreate, TeacherOut
from services.users import sync_accounts

router = APIRouter(prefix="/teachers", tags=["Profesores"])


def email_in_use(db: Session, email: str, exclude_id: int | None = None) -> bool:
    query = db.query(Teacher).filter(func.lower(Teacher.email) == email.lower())
    if exclude_id is not None:
        query = query.filter(Teacher.id != exclude_id)
    return query.first() is not None


@router.post("", response_model=TeacherOut)
def create_teacher(data: TeacherCreate, db: Session = Depends(get_db)):
    if email_in_use(db, data.email):
        raise HTTPException(status_code=409, detail="Ya existe un profesor con ese correo")

    teacher = Teacher(**data.model_dump())
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    sync_accounts(db)  # the teacher can sign in with this email from now on
    return teacher


@router.get("", response_model=List[TeacherOut])
def list_teachers(db: Session = Depends(get_db)):
    return db.query(Teacher).all()


@router.put("/{teacher_id}", response_model=TeacherOut)
def update_teacher(teacher_id: int, data: TeacherCreate, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")

    if email_in_use(db, data.email, exclude_id=teacher_id):
        raise HTTPException(status_code=409, detail="Ya existe otro profesor con ese correo")

    teacher.nombre = data.nombre
    teacher.email = data.email
    db.commit()
    db.refresh(teacher)
    sync_accounts(db)
    return teacher


@router.delete("/{teacher_id}")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")

    has_subjects = db.query(Subject).filter(Subject.profesor_id == teacher_id).first()
    if has_subjects:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar: el profesor tiene materias asignadas. Elimina o reasigna esas materias primero.",
        )

    db.delete(teacher)
    db.commit()
    sync_accounts(db)  # removes the teacher's account
    return {"mensaje": "Profesor eliminado"}
