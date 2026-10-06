from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from services.seed import delete_all, has_data, load_demo_data, load_faculty_data

router = APIRouter(tags=["Datos de demostración"])

DATASETS = {"demo": load_demo_data, "facultad": load_faculty_data}


@router.post("/seed")
def load_seed(
    # The public query parameter stays "reiniciar" (/seed?reiniciar=true)
    reset: bool = Query(False, alias="reiniciar"),
    # "demo" (small) or "facultad" (8 semesters of Software Engineering)
    dataset: str = "demo",
    db: Session = Depends(get_db),
):
    if dataset not in DATASETS:
        raise HTTPException(status_code=422, detail="dataset debe ser 'demo' o 'facultad'")
    if has_data(db):
        if not reset:
            raise HTTPException(
                status_code=409,
                detail="Ya hay datos cargados. Usa /seed?reiniciar=true para borrarlos y cargar los de demostración.",
            )
        delete_all(db)

    summary = DATASETS[dataset](db)
    return {
        "mensaje": "Datos de demostración cargados. Ahora pulsa 'Generar horario'.",
        "resumen": summary,
    }
