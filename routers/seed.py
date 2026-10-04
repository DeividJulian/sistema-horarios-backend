from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.seed import borrar_todo, cargar_datos_demo, hay_datos

router = APIRouter(tags=["Datos de demostración"])


@router.post("/seed")
def cargar_seed(reiniciar: bool = False, db: Session = Depends(get_db)):
    if hay_datos(db):
        if not reiniciar:
            raise HTTPException(
                status_code=409,
                detail="Ya hay datos cargados. Usa /seed?reiniciar=true para borrarlos y cargar los de demostración.",
            )
        borrar_todo(db)

    resumen = cargar_datos_demo(db)
    return {
        "mensaje": "Datos de demostración cargados. Ahora pulsa 'Generar horario'.",
        "resumen": resumen,
    }
