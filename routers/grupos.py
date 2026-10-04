from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Grupo, Materia
from schemas import GrupoCreate, GrupoOut

router = APIRouter(prefix="/grupos", tags=["Grupos"])


@router.post("", response_model=GrupoOut)
def crear_grupo(grupo: GrupoCreate, db: Session = Depends(get_db)):
    nuevo = Grupo(**grupo.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.get("", response_model=List[GrupoOut])
def listar_grupos(db: Session = Depends(get_db)):
    return db.query(Grupo).all()


@router.put("/{grupo_id}", response_model=GrupoOut)
def actualizar_grupo(grupo_id: int, datos: GrupoCreate, db: Session = Depends(get_db)):
    grupo = db.query(Grupo).filter(Grupo.id == grupo_id).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    grupo.nombre = datos.nombre
    grupo.num_estudiantes = datos.num_estudiantes
    db.commit()
    db.refresh(grupo)
    return grupo


@router.delete("/{grupo_id}")
def eliminar_grupo(grupo_id: int, db: Session = Depends(get_db)):
    grupo = db.query(Grupo).filter(Grupo.id == grupo_id).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    tiene_materias = db.query(Materia).filter(Materia.grupo_id == grupo_id).first()
    if tiene_materias:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar: el grupo tiene materias asignadas. Elimina esas materias primero.",
        )

    db.delete(grupo)
    db.commit()
    return {"mensaje": "Grupo eliminado"}
