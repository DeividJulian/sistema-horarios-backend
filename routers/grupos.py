from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import StudentGroup, Subject
from schemas import GroupCreate, GroupOut

router = APIRouter(prefix="/grupos", tags=["Grupos"])


@router.post("", response_model=GroupOut)
def crear_grupo(group: GroupCreate, db: Session = Depends(get_db)):
    nuevo = StudentGroup(**group.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.get("", response_model=List[GroupOut])
def listar_grupos(db: Session = Depends(get_db)):
    return db.query(StudentGroup).all()


@router.put("/{grupo_id}", response_model=GroupOut)
def actualizar_grupo(grupo_id: int, datos: GroupCreate, db: Session = Depends(get_db)):
    group = db.query(StudentGroup).filter(StudentGroup.id == grupo_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    group.nombre = datos.nombre
    group.num_estudiantes = datos.num_estudiantes
    db.commit()
    db.refresh(group)
    return group


@router.delete("/{grupo_id}")
def eliminar_grupo(grupo_id: int, db: Session = Depends(get_db)):
    group = db.query(StudentGroup).filter(StudentGroup.id == grupo_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    tiene_materias = db.query(Subject).filter(Subject.grupo_id == grupo_id).first()
    if tiene_materias:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar: el grupo tiene materias asignadas. Elimina esas materias primero.",
        )

    db.delete(group)
    db.commit()
    return {"mensaje": "Grupo eliminado"}
