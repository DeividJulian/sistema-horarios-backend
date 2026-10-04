from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from services.seed import delete_all, has_data, load_demo_data

router = APIRouter(tags=["Datos de demostración"])


@router.post("/seed")
def load_seed(
    # The public query parameter stays "reiniciar" (/seed?reiniciar=true)
    reset: bool = Query(False, alias="reiniciar"),
    db: Session = Depends(get_db),
):
    if has_data(db):
        if not reset:
            raise HTTPException(
                status_code=409,
                detail="Ya hay datos cargados. Usa /seed?reiniciar=true para borrarlos y cargar los de demostración.",
            )
        delete_all(db)

    summary = load_demo_data(db)
    return {
        "mensaje": "Datos de demostración cargados. Ahora pulsa 'Generar horario'.",
        "resumen": summary,
    }
