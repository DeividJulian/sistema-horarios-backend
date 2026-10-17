from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from database import get_db
from models import User
from security import deny_students
from services import ai

# Students only see their group, so the faculty-wide explanation is not for them
router = APIRouter(prefix="/ai", tags=["Inteligencia artificial"])


class ExplainRequest(BaseModel):
    pregunta: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


@router.get("/status")
def status(_: User = Depends(deny_students)):
    """Whether the AI layer is configured (ANTHROPIC_API_KEY present) and which model it uses."""
    return {"disponible": ai.is_available(), "modelo": ai.MODEL if ai.is_available() else None}


@router.post("/explain")
def explain(data: ExplainRequest | None = None, db: Session = Depends(get_db), _: User = Depends(deny_students)):
    """Claude explains the state of the schedule (why it fails, what to fix) from the system's own data."""
    try:
        return ai.explain(db, data.pregunta if data else None)
    except ai.AIUnavailable:
        raise HTTPException(
            status_code=503,
            detail="La IA no está configurada: falta la variable ANTHROPIC_API_KEY en el servidor.",
        )
    except ai.AIError as error:
        raise HTTPException(status_code=502, detail=str(error))
