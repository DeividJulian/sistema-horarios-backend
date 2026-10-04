from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services.conflictos import detectar_conflictos
from services.estadisticas import calcular_estadisticas

router = APIRouter(tags=["Análisis"])


@router.get("/conflictos")
def obtener_conflictos(db: Session = Depends(get_db)):
    conflictos = detectar_conflictos(db)
    return {
        "total": len(conflictos),
        "hay_conflictos": len(conflictos) > 0,
        "conflictos": conflictos,
    }


@router.get("/estadisticas")
def obtener_estadisticas(db: Session = Depends(get_db)):
    return calcular_estadisticas(db)
