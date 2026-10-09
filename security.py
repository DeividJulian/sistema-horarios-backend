"""Password hashing, JWT tokens and the dependencies that protect the endpoints by role."""
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import DATABASE_URL, get_db
from models import User

logger = logging.getLogger("schedule.auth")

ALGORITHM = "HS256"
TOKEN_HOURS = 8
PBKDF2_ROUNDS = 260_000

# JWT_SECRET should be set in production. Without it the secret is derived from DATABASE_URL, which is
# already private and stable across restarts (a random one would log everybody out on every Render restart).
SECRET_KEY = os.getenv("JWT_SECRET") or hashlib.sha256(f"jwt::{DATABASE_URL}".encode()).hexdigest()

READ_METHODS = {"GET", "HEAD", "OPTIONS"}

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ROUNDS).hex()
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
    return hmac.compare_digest(candidate, digest)


def create_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user.id), "rol": user.rol, "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)


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
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo un administrador puede hacer esta acción.")
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
