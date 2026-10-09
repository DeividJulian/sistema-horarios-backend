from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.backup import backup_info, discard_backup, restore_backup, save_backup
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
                detail="Ya hay datos cargados. Usa /seed?reset=true para reemplazarlos por los de demostración (se guarda una copia).",
            )
        save_backup(db)  # the way back: POST /seed/restore
        delete_all(db)

    summary = DATASETS[dataset](db)
    sync_accounts(db)  # one account per new teacher, and the demo student in one of the new groups
    return {
        "mensaje": "Datos de demostración cargados. Ahora pulsa 'Generar horario'.",
        "resumen": summary,
        "respaldo": backup_info(db),
    }


@router.get("/seed/backup")
def get_backup(db: Session = Depends(get_db)):
    """Whether there is a copy of the data replaced by the demo, when it was taken and what it holds."""
    return backup_info(db)


@router.post("/seed/restore")
def restore(db: Session = Depends(get_db)):
    """Goes back to the data that was there before loading the demo."""
    summary = restore_backup(db)
    if summary is None:
        raise HTTPException(status_code=404, detail="No hay una copia de tus datos para restaurar.")
    return {"mensaje": "Tus datos volvieron a como estaban antes de cargar la demostración.", "resumen": summary}


@router.delete("/seed/backup")
def delete_backup(db: Session = Depends(get_db)):
    """Keeps the demo data and forgets the copy."""
    discard_backup(db)
    return {"mensaje": "Copia descartada"}
