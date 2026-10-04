from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Aula, Horario
from schemas import AulaCreate, AulaOut

router = APIRouter(prefix="/aulas", tags=["Aulas"])


@router.post("", response_model=AulaOut)
def crear_aula(aula: AulaCreate, db: Session = Depends(get_db)):
    nueva = Aula(**aula.dict())
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
