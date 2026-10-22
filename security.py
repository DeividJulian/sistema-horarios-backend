"""JWT session tokens and the dependencies that protect the endpoints by role."""
import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

import config
from database import get_db
from models import User

logger = logging.getLogger("schedule.auth")

ALGORITHM = "HS256"

READ_METHODS = {"GET", "HEAD", "OPTIONS"}

bearer = HTTPBearer(auto_error=False)


def create_token(user: User, hours: float | None = None) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_HOURS if hours is None else hours)
    return jwt.encode({"sub": str(user.id), "rol": user.rol, "exp": expires}, config.SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.", headers={"WWW-Authenticate": "Bearer"})
    unauthorized = HTTPException(
        status_code=401,
        detail="Tu sesión no es válida o expiró. Inicia sesión de nuevo.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, config.SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    # An account that never entered its first code can not be used yet
    if user is None or not user.verificado:
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo un administrador puede hacer esta acción.")
    return user


def deny_students(user: User = Depends(get_current_user)) -> User:
    """The faculty-wide analysis is not for students (they only see their own group's schedule)."""
    if user.rol == "estudiante":
        raise HTTPException(status_code=403, detail="Esta sección no está disponible para estudiantes.")
    return user


def authorize(request: Request, user: User = Depends(get_current_user)) -> User:
    """Data endpoints: any signed-in user may read, only administrators may change data."""
    if request.method not in READ_METHODS and user.rol != "admin":
        logger.warning("User %s (%s) tried %s %s", user.email, user.rol, request.method, request.url.path)
        raise HTTPException(
            status_code=403,
            detail="Tu rol es de solo lectura: solo un administrador puede modificar datos.",
        )
    return user
