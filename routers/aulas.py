from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Aula
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
