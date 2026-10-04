from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Aula, Horario
from schemas import AulaCreate, AulaOut

router = APIRouter(prefix="/aulas", tags=["Aulas"])


def nombre_en_uso(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    consulta = db.query(Aula).filter(func.lower(Aula.nombre) == nombre.lower())
    if excluir_id is not None:
        consulta = consulta.filter(Aula.id != excluir_id)
    return consulta.first() is not None


@router.post("", response_model=AulaOut)
def crear_aula(aula: AulaCreate, db: Session = Depends(get_db)):
    if nombre_en_uso(db, aula.nombre):
        raise HTTPException(status_code=409, detail="Ya existe un aula con ese nombre")

    nueva = Aula(**aula.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.get("", response_model=List[AulaOut])
def listar_aulas(db: Session = Depends(get_db)):
    return db.query(Aula).all()


@router.put("/{aula_id}", response_model=AulaOut)
def actualizar_aula(aula_id: int, datos: AulaCreate, db: Session = Depends(get_db)):
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    if nombre_en_uso(db, datos.nombre, excluir_id=aula_id):
        raise HTTPException(status_code=409, detail="Ya existe otra aula con ese nombre")

    aula.nombre = datos.nombre
    aula.aforo = datos.aforo
    db.commit()
    db.refresh(aula)
    return aula


@router.delete("/{aula_id}")
def eliminar_aula(aula_id: int, db: Session = Depends(get_db)):
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    en_uso = db.query(Horario).filter(Horario.aula_id == aula_id).first()
    if en_uso:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar: el aula tiene clases programadas en el horario actual.",
        )

    db.delete(aula)
    db.commit()
    return {"mensaje": "Aula eliminada"}
