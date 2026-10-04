from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Profesor
from schemas import ProfesorCreate, ProfesorOut

router = APIRouter(prefix="/profesores", tags=["Profesores"])


@router.post("", response_model=ProfesorOut)
def crear_profesor(profesor: ProfesorCreate, db: Session = Depends(get_db)):
    nuevo = Profesor(**profesor.dict())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.get("", response_model=List[ProfesorOut])
def listar_profesores(db: Session = Depends(get_db)):
    return db.query(Profesor).all()
