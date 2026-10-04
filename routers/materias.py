from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Grupo, Horario, Materia, Profesor
from schemas import MateriaCreate, MateriaOut

router = APIRouter(prefix="/materias", tags=["Materias"])


def validar_referencias(materia: MateriaCreate, db: Session):
    grupo = db.query(Grupo).filter(Grupo.id == materia.grupo_id).first()
    profesor = db.query(Profesor).filter(Profesor.id == materia.profesor_id).first()
    if not grupo or not profesor:
        raise HTTPException(status_code=404, detail="Grupo o profesor no encontrado")


@router.post("", response_model=MateriaOut)
def crear_materia(materia: MateriaCreate, db: Session = Depends(get_db)):
    validar_referencias(materia, db)
    nueva = Materia(**materia.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.get("", response_model=List[MateriaOut])
def listar_materias(db: Session = Depends(get_db)):
    return db.query(Materia).all()


@router.put("/{materia_id}", response_model=MateriaOut)
def actualizar_materia(materia_id: int, datos: MateriaCreate, db: Session = Depends(get_db)):
    materia = db.query(Materia).filter(Materia.id == materia_id).first()
    if not materia:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    validar_referencias(datos, db)

    materia.nombre = datos.nombre
    materia.intensidad_horaria = datos.intensidad_horaria
    materia.grupo_id = datos.grupo_id
    materia.profesor_id = datos.profesor_id
    db.commit()
    db.refresh(materia)
    return materia


@router.delete("/{materia_id}")
def eliminar_materia(materia_id: int, db: Session = Depends(get_db)):
    materia = db.query(Materia).filter(Materia.id == materia_id).first()
    if not materia:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    # Los bloques de horario de esta materia quedarian huerfanos, asi que se eliminan primero
    db.query(Horario).filter(Horario.materia_id == materia_id).delete()
    db.delete(materia)
    db.commit()
    return {"mensaje": "Materia eliminada junto con sus bloques de horario"}
