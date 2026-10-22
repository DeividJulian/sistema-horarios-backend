import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Classroom, ScheduleEntry, User
from schemas import AIStatus, ConflictSuggestion, NoticeDraftOut, NoticeDraftRequest
from security import deny_students, require_admin
from services import ai, llm
from services.class_changes import get_entry_for_change

logger = logging.getLogger("schedule.ai")

# The AI only advises: these endpoints never change data. Students do not use it.
router = APIRouter(prefix="/ai", tags=["IA"])


def _run(function, *args):
    """Turns model errors into clear HTTP responses (never a 500)."""
    try:
        return function(*args)
    except llm.LLMNotConfigured as e:
        raise HTTPException(status_code=503, detail=f"La IA no está configurada: {e}.")
    except llm.LLMRateLimited as e:
        headers = {"Retry-After": e.retry_after} if e.retry_after else None
        raise HTTPException(status_code=429, detail=str(e), headers=headers)
    except llm.LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # an unexpected answer must not become a 500 either
        logger.error("Unexpected AI failure", exc_info=e)
        raise HTTPException(status_code=502, detail="La IA no pudo responder. Intenta de nuevo.")


@router.get("/status", response_model=AIStatus, dependencies=[Depends(deny_students)])
def ai_status():
    """Whether the AI is configured, with which provider and model (the frontend shows the provider named here)."""
    config = llm.current_config()
    return {
        "configurada": llm.is_configured(),
        "proveedor": config.provider,
        "nombre_proveedor": config.label,
        "modelo": config.model,
    }


@router.post("/conflicts/{entry_id}/suggestion", response_model=ConflictSuggestion, dependencies=[Depends(require_admin)])
def conflict_suggestion(entry_id: int, db: Session = Depends(get_db)):
    """Valid slots and classrooms for a conflicting class, with the AI's recommendation. Nothing is moved."""
    entry = db.get(ScheduleEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    return _run(ai.suggest_for_conflict, db, entry)


@router.post("/notices/draft", response_model=NoticeDraftOut)
def notice_draft(data: NoticeDraftRequest, db: Session = Depends(get_db), user: User = Depends(deny_students)):
    """Draft of the notice for the students; the teacher reviews it before cancelling or changing the classroom."""
    entry = get_entry_for_change(db, data.horario_id, user)
    classroom = None
    if data.tipo == "cambio_aula":
        if data.aula_id is None:
            raise HTTPException(status_code=422, detail="Elige el aula nueva para redactar el aviso.")
        classroom = db.get(Classroom, data.aula_id)
        if classroom is None:
            raise HTTPException(status_code=404, detail="Aula no encontrada")
    return _run(ai.draft_notice, db, entry, data.tipo, data.fecha, classroom, data.motivo)
