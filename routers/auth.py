import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import LoginRequest, TokenOut, UserOut
from security import create_token, get_current_user, verify_password

logger = logging.getLogger("schedule.auth")

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=TokenOut)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if user is None or not verify_password(data.password, user.password_hash):
        logger.warning("Failed login for %s", data.email)
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    logger.info("Login: %s (%s)", user.email, user.rol)
    return {"access_token": create_token(user), "token_type": "bearer", "usuario": user}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
