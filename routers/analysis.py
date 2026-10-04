from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services.conflicts import detect_conflicts
from services.stats import compute_statistics

router = APIRouter(tags=["Análisis"])


@router.get("/conflictos")
def get_conflicts(db: Session = Depends(get_db)):
    conflicts = detect_conflicts(db)
    return {
        "total": len(conflicts),
        "hay_conflictos": len(conflicts) > 0,
        "conflictos": conflicts,
    }


@router.get("/estadisticas")
def get_statistics(db: Session = Depends(get_db)):
    return compute_statistics(db)
