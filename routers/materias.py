from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Grupo, Materia, Profesor
from schemas import MateriaCreate, MateriaOut

router = APIRouter(prefix="/materias", tags=["Materias"])


@router.post("", response_model=MateriaOut)
def crear_materia(materia: MateriaCreate, db: Session = Depends(get_db)):
    grupo = db.query(Grupo).filter(Grupo.id == materia.grupo_id).first()
    profesor = db.query(Profesor).filter(Profesor.id == materia.profesor_id).first()
    if not grupo or not profesor:
        raise HTTPException(status_code=404, detail="Grupo o profesor no encontrado")
    nueva = Materia(**materia.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.get("", response_model=List[MateriaOut])
def listar_materias(db: Session = Depends(get_db)):
    return db.query(Materia).all()
