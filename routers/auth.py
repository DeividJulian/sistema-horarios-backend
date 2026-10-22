import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import StudentGroup, Teacher, User
from schemas import CodeSent, LoginRequest, RegisterGroup, RegisterRequest, TokenOut, UserOut, VerifyRequest
from security import create_token, get_current_user
from services.codes import CodeCooldown, InvalidCode, check_code, find_user, issue_code, normalize_email, send_code
from services.mailer import MailError

logger = logging.getLogger("schedule.auth")

router = APIRouter(prefix="/auth", tags=["Autenticación"])


def _send_new_code(db: Session, user: User, purpose: str) -> None:
    """Creates and emails the code. If the email doesn't go out, everything is undone (no half-made account)."""
    try:
        code = issue_code(db, user, purpose)
    except CodeCooldown as e:
        db.rollback()
        raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": str(e.seconds)})
    try:
        send_code(user, code, purpose)
    except MailError:
        db.rollback()
        raise HTTPException(status_code=502, detail="No pudimos enviar el correo. Inténtalo de nuevo en unos minutos.")
    db.commit()


@router.get("/register-options", response_model=List[RegisterGroup])
def register_options(db: Session = Depends(get_db)):
    """Groups a student can choose when signing up (public: the sign-up form needs them)."""
    return db.query(StudentGroup).order_by(StudentGroup.nombre).all()


@router.post("/register", response_model=CodeSent, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """Students create their account choosing their group; it stays unverified until they enter the emailed code.

    If the account exists but was never verified, the code is sent again. Nobody signs up as administrator,
    and teachers already have an account with the email the administrator registered: they just sign in.
    """
    email = normalize_email(data.email)
    user = find_user(db, email)
    if user and user.verificado:
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo. Inicia sesión.")
    if (user and user.rol != "estudiante") or db.query(Teacher).filter(func.lower(Teacher.email) == email).first():
        raise HTTPException(
            status_code=409,
            detail="Ese correo ya tiene una cuenta de profesor o del personal: inicia sesión con él y te enviaremos un código.",
        )
    if db.get(StudentGroup, data.grupo_id) is None:
        raise HTTPException(status_code=404, detail="El grupo elegido no existe.")
    if user:
        user.nombre = data.nombre
        user.grupo_id = data.grupo_id
    else:
        user = User(nombre=data.nombre, email=email, rol="estudiante", grupo_id=data.grupo_id)
        db.add(user)
        db.flush()
    _send_new_code(db, user, "registro")
    logger.info("Sign-up: %s (code sent)", email)
    return {"mensaje": "Te enviamos un código para activar tu cuenta.", "email": user.email}


@router.post("/login", response_model=CodeSent)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """Emails a one-time code to enter."""
    user = find_user(db, data.email)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="No hay una cuenta con ese correo. Si eres estudiante, regístrate; si eres profesor, pide al administrador que te registre.",
        )
    _send_new_code(db, user, "login")
    return {"mensaje": "Te enviamos un código para entrar.", "email": user.email}


@router.post("/verify", response_model=TokenOut)
def verify(data: VerifyRequest, db: Session = Depends(get_db)):
    """Checks the emailed code and returns the session token. The first time it activates the account."""
    user = find_user(db, data.email)
    if user is None:
        raise HTTPException(status_code=400, detail="No hay un código activo: pide uno nuevo.")
    try:
        check_code(db, user, data.codigo)
    except InvalidCode as e:
        db.commit()  # keeps the failed attempt or the invalidated code
        raise HTTPException(status_code=400, detail=str(e))
    user.verificado = True
    db.commit()
    db.refresh(user)
    logger.info("Login: %s (%s)", user.email, user.rol)
    return {"access_token": create_token(user), "token_type": "bearer", "usuario": user}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
