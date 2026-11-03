from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas import ConflictReport, ReadinessOut, StatisticsOut
from security import deny_students
from services.conflicts import detect_conflicts
from services.readiness import check_readiness
from services.stats import compute_statistics

router = APIRouter(tags=["Análisis"], dependencies=[Depends(deny_students)])


@router.get("/conflicts", response_model=ConflictReport)
def get_conflicts(db: Session = Depends(get_db)):
    conflicts = detect_conflicts(db)
    return {
        "total": len(conflicts),
        "hay_conflictos": len(conflicts) > 0,
        "conflictos": conflicts,
    }


@router.get("/statistics", response_model=StatisticsOut)
def get_statistics(db: Session = Depends(get_db)):
    return compute_statistics(db)


@router.get("/diagnostics", response_model=ReadinessOut)
def get_readiness(db: Session = Depends(get_db)):
    """What would stop the generator, in plain language and with the section where it is fixed."""
    return check_readiness(db)
