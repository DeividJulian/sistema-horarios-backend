from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import DisponibilidadProfesor, Profesor
from schemas import DisponibilidadCreate, DisponibilidadOut

router = APIRouter(prefix="/disponibilidad", tags=["Disponibilidad"])


@router.post("", response_model=DisponibilidadOut)
def crear_disponibilidad(disp: DisponibilidadCreate, db: Session = Depends(get_db)):
    profesor = db.query(Profesor).filter(Profesor.id == disp.profesor_id).first()
    if not profesor:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")
    nueva = DisponibilidadProfesor(**disp.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.get("/{profesor_id}", response_model=List[DisponibilidadOut])
def listar_disponibilidad(profesor_id: int, db: Session = Depends(get_db)):
    return (
        db.query(DisponibilidadProfesor)
        .filter(DisponibilidadProfesor.profesor_id == profesor_id)
        .all()
    )


@router.delete("/{disponibilidad_id}")
def eliminar_disponibilidad(disponibilidad_id: int, db: Session = Depends(get_db)):
    disp = (
        db.query(DisponibilidadProfesor)
        .filter(DisponibilidadProfesor.id == disponibilidad_id)
        .first()
    )
    if not disp:
        raise HTTPException(status_code=404, detail="Disponibilidad no encontrada")

    db.delete(disp)
    db.commit()
    return {"mensaje": "Disponibilidad eliminada"}
