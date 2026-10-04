from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import StudentGroup, ScheduleEntry, Subject, Teacher
from schemas import SubjectCreate, SubjectOut

router = APIRouter(prefix="/materias", tags=["Materias"])


def validar_referencias(subject: SubjectCreate, db: Session):
    group = db.query(StudentGroup).filter(StudentGroup.id == subject.grupo_id).first()
    teacher = db.query(Teacher).filter(Teacher.id == subject.profesor_id).first()
    if not group or not teacher:
        raise HTTPException(status_code=404, detail="Grupo o profesor no encontrado")


@router.post("", response_model=SubjectOut)
def crear_materia(subject: SubjectCreate, db: Session = Depends(get_db)):
    validar_referencias(subject, db)
    nueva = Subject(**subject.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.get("", response_model=List[SubjectOut])
def listar_materias(db: Session = Depends(get_db)):
    return db.query(Subject).all()


@router.put("/{materia_id}", response_model=SubjectOut)
def actualizar_materia(materia_id: int, datos: SubjectCreate, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == materia_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    validar_referencias(datos, db)

    subject.nombre = datos.nombre
    subject.intensidad_horaria = datos.intensidad_horaria
    subject.grupo_id = datos.grupo_id
    subject.profesor_id = datos.profesor_id
    db.commit()
    db.refresh(subject)
    return subject


@router.delete("/{materia_id}")
def eliminar_materia(materia_id: int, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == materia_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    # Los bloques de horario de esta materia quedarian huerfanos, asi que se eliminan primero
    db.query(ScheduleEntry).filter(ScheduleEntry.materia_id == materia_id).delete()
    db.delete(subject)
    db.commit()
    return {"mensaje": "Materia eliminada junto con sus bloques de horario"}
