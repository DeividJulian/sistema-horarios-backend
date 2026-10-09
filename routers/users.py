from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import UserCreate, UserOut
from security import hash_password, require_admin

# Only administrators manage the accounts
router = APIRouter(prefix="/users", tags=["Usuarios"])


@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).order_by(User.id).all()


@router.post("", response_model=UserOut)
def create_user(data: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    email = data.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo.")
    user = User(nombre=data.nombre, email=email, password_hash=hash_password(data.password), rol=data.rol)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.id == current.id:
        raise HTTPException(status_code=409, detail="No puedes eliminar tu propia cuenta.")
    db.delete(user)
    db.commit()
    return {"mensaje": "Usuario eliminado"}
