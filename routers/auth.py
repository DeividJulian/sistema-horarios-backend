import logging
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import DemoAccount, LoginRequest, PasswordChange, TokenOut, UserOut
from security import create_token, get_current_user, hash_password, verify_password
from services.users import DEFAULT_USERS, TEACHER_PASSWORD, demo_teacher

logger = logging.getLogger("schedule.auth")

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# The login page shows buttons to try every role. Set DEMO_ACCOUNTS=false to hide them in a real deployment.
SHOW_DEMO_ACCOUNTS = os.getenv("DEMO_ACCOUNTS", "true").lower() != "false"


@router.post("/login", response_model=TokenOut)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    if user is None or not verify_password(data.password, user.password_hash):
        logger.warning("Failed login for %s", data.email)
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    logger.info("Login: %s (%s)", user.email, user.rol)
    return {"access_token": create_token(user), "token_type": "bearer", "usuario": user}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password")
def change_password(data: PasswordChange, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(data.actual, user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta.")
    if data.actual == data.nueva:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe ser distinta de la actual.")
    user.password_hash = hash_password(data.nueva)
    db.commit()
    logger.info("Password changed: %s", user.email)
    return {"mensaje": "Contraseña actualizada"}


@router.get("/demo-accounts", response_model=List[DemoAccount])
def demo_accounts(db: Session = Depends(get_db)):
    """Test accounts for each role (public, so the login page can offer them)."""
    if not SHOW_DEMO_ACCOUNTS:
        return []
    admin, reader, student = DEFAULT_USERS
    accounts = [
        {"rol": "admin", "etiqueta": "Administrador", "descripcion": "Gestiona todo", "email": admin["email"], "password": admin["password"]},
    ]
    teacher = demo_teacher(db)
    if teacher is not None:
        accounts.append(
            {"rol": "profesor", "etiqueta": "Profesor", "descripcion": teacher.nombre, "email": teacher.email.lower(), "password": TEACHER_PASSWORD}
        )
    accounts.append(
        {"rol": "estudiante", "etiqueta": "Estudiante", "descripcion": "Ve el horario de su grupo", "email": student["email"], "password": student["password"]}
    )
    accounts.append(
        {"rol": "usuario", "etiqueta": "Consulta", "descripcion": "Solo lectura", "email": reader["email"], "password": reader["password"]}
    )
    return accounts
