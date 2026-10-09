from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import StudentGroup, Subject
from schemas import GroupCreate, GroupOut

router = APIRouter(prefix="/groups", tags=["Grupos"])


@router.post("", response_model=GroupOut)
def create_group(data: GroupCreate, db: Session = Depends(get_db)):
    group = StudentGroup(**data.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get("", response_model=List[GroupOut])
def list_groups(db: Session = Depends(get_db)):
    return db.query(StudentGroup).all()


@router.put("/{group_id}", response_model=GroupOut)
def update_group(group_id: int, data: GroupCreate, db: Session = Depends(get_db)):
    group = db.query(StudentGroup).filter(StudentGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    group.nombre = data.nombre
    group.num_estudiantes = data.num_estudiantes
    group.jornada = data.jornada
    db.commit()
    db.refresh(group)
    return group


@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(StudentGroup).filter(StudentGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    has_subjects = db.query(Subject).filter(Subject.grupo_id == group_id).first()
    if has_subjects:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar: el grupo tiene materias asignadas. Elimina esas materias primero.",
        )

    db.delete(group)
    db.commit()
    return {"mensaje": "Grupo eliminado"}
