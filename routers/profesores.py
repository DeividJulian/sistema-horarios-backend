from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Materia, Profesor
from schemas import ProfesorCreate, ProfesorOut

router = APIRouter(prefix="/profesores", tags=["Profesores"])


def correo_en_uso(db: Session, email: str, excluir_id: int | None = None) -> bool:
    consulta = db.query(Profesor).filter(func.lower(Profesor.email) == email.lower())
    if excluir_id is not None:
        consulta = consulta.filter(Profesor.id != excluir_id)
    return consulta.first() is not None


@router.post("", response_model=ProfesorOut)
def crear_profesor(profesor: ProfesorCreate, db: Session = Depends(get_db)):
    if correo_en_uso(db, profesor.email):
        raise HTTPException(status_code=409, detail="Ya existe un profesor con ese correo")

    nuevo = Profesor(**profesor.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.get("", response_model=List[ProfesorOut])
def listar_profesores(db: Session = Depends(get_db)):
    return db.query(Profesor).all()


@router.put("/{profesor_id}", response_model=ProfesorOut)
def actualizar_profesor(profesor_id: int, datos: ProfesorCreate, db: Session = Depends(get_db)):
    profesor = db.query(Profesor).filter(Profesor.id == profesor_id).first()
    if not profesor:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")

    if correo_en_uso(db, datos.email, excluir_id=profesor_id):
        raise HTTPException(status_code=409, detail="Ya existe otro profesor con ese correo")

    profesor.nombre = datos.nombre
    profesor.email = datos.email
    db.commit()
    db.refresh(profesor)
    return profesor


@router.delete("/{profesor_id}")
def eliminar_profesor(profesor_id: int, db: Session = Depends(get_db)):
    profesor = db.query(Profesor).filter(Profesor.id == profesor_id).first()
    if not profesor:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")

    tiene_materias = db.query(Materia).filter(Materia.profesor_id == profesor_id).first()
    if tiene_materias:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar: el profesor tiene materias asignadas. Elimina o reasigna esas materias primero.",
        )

    db.delete(profesor)
    db.commit()
    return {"mensaje": "Profesor eliminado"}
