from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.seed import delete_all, load_demo_data, has_data

router = APIRouter(tags=["Datos de demostración"])


@router.post("/seed")
def cargar_seed(reiniciar: bool = False, db: Session = Depends(get_db)):
    if has_data(db):
        if not reiniciar:
            raise HTTPException(
                status_code=409,
                detail="Ya hay datos cargados. Usa /seed?reiniciar=true para borrarlos y cargar los de demostración.",
            )
        delete_all(db)

    resumen = load_demo_data(db)
    return {
        "mensaje": "Datos de demostración cargados. Ahora pulsa 'Generar horario'.",
        "resumen": resumen,
    }
