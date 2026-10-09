from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.seed import delete_all, has_data, load_demo_data, load_faculty_data
from services.users import sync_accounts

router = APIRouter(tags=["Datos de demostración"])

DATASETS = {"demo": load_demo_data, "faculty": load_faculty_data}


@router.post("/seed")
def load_seed(
    reset: bool = False,
    # "demo" (small) or "faculty" (8 semesters of Software Engineering)
    dataset: str = "demo",
    db: Session = Depends(get_db),
):
    if dataset not in DATASETS:
        raise HTTPException(status_code=422, detail="dataset debe ser 'demo' o 'faculty'")
    if has_data(db):
        if not reset:
            raise HTTPException(
                status_code=409,
                detail="Ya hay datos cargados. Usa /seed?reset=true para borrarlos y cargar los de demostración.",
            )
        delete_all(db)

    summary = DATASETS[dataset](db)
    sync_accounts(db)  # one account per new teacher, and the demo student in one of the new groups
    return {
        "mensaje": "Datos de demostración cargados. Ahora pulsa 'Generar horario'.",
        "resumen": summary,
    }
