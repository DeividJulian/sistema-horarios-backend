from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import StudentGroup, Teacher, User
from schemas import UserCreate, UserGroupChange, UserOut
from security import hash_password, require_admin

# Only administrators manage the accounts
router = APIRouter(prefix="/users", tags=["Usuarios"])


def _check_group(db: Session, group_id: int) -> None:
    if db.get(StudentGroup, group_id) is None:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")


@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).order_by(User.id).all()


@router.post("", response_model=UserOut)
def create_user(data: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    email = data.email.lower()
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo.")
    if data.rol == "estudiante":
        _check_group(db, data.grupo_id)
    if data.rol == "profesor":
        if db.get(Teacher, data.profesor_id) is None:
            raise HTTPException(status_code=404, detail="Profesor no encontrado")
        if db.query(User).filter(User.profesor_id == data.profesor_id).first():
            raise HTTPException(status_code=409, detail="Ese profesor ya tiene una cuenta.")
    user = User(
        nombre=data.nombre,
        email=email,
        password_hash=hash_password(data.password),
        rol=data.rol,
        profesor_id=data.profesor_id if data.rol == "profesor" else None,
        grupo_id=data.grupo_id if data.rol == "estudiante" else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/group", response_model=UserOut)
def change_group(user_id: int, data: UserGroupChange, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Moves a student to another group (for example when they pass to the next semester)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.rol != "estudiante":
        raise HTTPException(status_code=409, detail="Solo los estudiantes tienen grupo.")
    _check_group(db, data.grupo_id)
    user.grupo_id = data.grupo_id
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
    if user.rol == "profesor":
        raise HTTPException(
            status_code=409,
            detail="Las cuentas de profesor se crean y eliminan junto con el profesor (Gestión → Profesores).",
        )
    db.delete(user)
    db.commit()
    return {"mensaje": "Usuario eliminado"}
