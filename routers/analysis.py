from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services.conflicts import detect_conflicts
from services.readiness import check_readiness
from services.stats import compute_statistics

router = APIRouter(tags=["Análisis"])


@router.get("/conflicts")
def get_conflicts(db: Session = Depends(get_db)):
    conflicts = detect_conflicts(db)
    return {
        "total": len(conflicts),
        "hay_conflictos": len(conflicts) > 0,
        "conflictos": conflicts,
    }


@router.get("/statistics")
def get_statistics(db: Session = Depends(get_db)):
    return compute_statistics(db)


@router.get("/diagnostics")
def get_readiness(db: Session = Depends(get_db)):
    """What would stop the generator, in plain language and with the section where it is fixed."""
    return check_readiness(db)
