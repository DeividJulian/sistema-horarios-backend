from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Cancellation, Notification, ScheduleEntry, Subject, User
from schemas import CancellationCreate, CancellationOut, ClassroomChange, NotificationOut, ScheduleEntryOut
from security import get_current_user
from services.class_changes import cancel_class, change_classroom, get_entry_for_change, restore_class, today

# Teachers adjust their own classes (administrators can adjust any); every signed-in user reads
# the cancellations and notices that apply to them.
router = APIRouter(tags=["Cambios de clase y avisos"])


@router.post("/schedules/{entry_id}/cancellations", response_model=CancellationOut)
def create_cancellation(
    entry_id: int,
    data: CancellationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = get_entry_for_change(db, entry_id, user)
    return cancel_class(db, entry, data.fecha, data.motivo, user)


@router.delete("/cancellations/{cancellation_id}")
def delete_cancellation(cancellation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cancellation = db.get(Cancellation, cancellation_id)
    if cancellation is None:
        raise HTTPException(status_code=404, detail="Cancelación no encontrada")
    get_entry_for_change(db, cancellation.horario_id, user)
    restore_class(db, cancellation)
    return {"mensaje": "Clase restablecida"}


@router.get("/cancellations", response_model=List[CancellationOut])
def list_cancellations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Cancellations from last week on (enough to draw this week and the next ones)."""
    query = db.query(Cancellation).filter(Cancellation.fecha >= today() - timedelta(days=7))
    if user.rol == "estudiante":
        query = (
            query.join(ScheduleEntry, Cancellation.horario_id == ScheduleEntry.id)
            .join(Subject, ScheduleEntry.materia_id == Subject.id)
            .filter(Subject.grupo_id == user.grupo_id)
        )
    return query.order_by(Cancellation.fecha).all()


@router.patch("/schedules/{entry_id}/classroom", response_model=ScheduleEntryOut)
def update_classroom(
    entry_id: int,
    data: ClassroomChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = get_entry_for_change(db, entry_id, user)
    return change_classroom(db, entry, data.aula_id)


@router.get("/notifications", response_model=List[NotificationOut])
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Students: their group's notices. Teachers: the ones about their subjects. Others: all of them."""
    query = db.query(Notification)
    if user.rol == "estudiante":
        query = query.filter(Notification.grupo_id == user.grupo_id)
    elif user.rol == "profesor":
        own_subjects = db.query(Subject.id).filter(Subject.profesor_id == user.profesor_id)
        query = query.filter(Notification.materia_id.in_(own_subjects))
    return query.order_by(Notification.creada_en.desc(), Notification.id.desc()).limit(50).all()
