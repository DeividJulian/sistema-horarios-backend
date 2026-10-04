from datetime import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Aula, Horario, Materia, Profesor
from schemas import HorarioOut, HorarioUpdate
from services.csp import calcular_asignaciones

router = APIRouter(tags=["Horarios"])


@router.post("/generar-horario")
def generar_horario(db: Session = Depends(get_db)):
    exito, asignaciones, mensaje = calcular_asignaciones(db)
    if not exito:
        raise HTTPException(status_code=409, detail=mensaje)

    db.query(Horario).delete()
    for materia, aula, dia, hora in asignaciones:
        db.add(
            Horario(
                materia_id=materia.id,
                aula_id=aula.id,
                dia_semana=dia,
                hora_inicio=hora,
                hora_fin=time(hour=hora.hour + 1),
            )
        )
    db.commit()
    return {"mensaje": "Horario generado exitosamente", "total_bloques": len(asignaciones)}


@router.get("/horarios", response_model=List[HorarioOut])
def listar_horarios(db: Session = Depends(get_db)):
    return db.query(Horario).all()


@router.get("/horarios/grupo/{grupo_id}", response_model=List[HorarioOut])
def horarios_por_grupo(grupo_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Horario)
        .join(Materia, Horario.materia_id == Materia.id)
        .filter(Materia.grupo_id == grupo_id)
        .all()
    )


@router.get("/horarios/profesor/{profesor_id}", response_model=List[HorarioOut])
def horarios_por_profesor(profesor_id: int, db: Session = Depends(get_db)):
    profesor = db.query(Profesor).filter(Profesor.id == profesor_id).first()
    if not profesor:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")

    return (
        db.query(Horario)
        .join(Materia, Horario.materia_id == Materia.id)
        .filter(Materia.profesor_id == profesor_id)
        .order_by(Horario.dia_semana, Horario.hora_inicio)
        .all()
    )


@router.get("/horarios/aula/{aula_id}", response_model=List[HorarioOut])
def horarios_por_aula(aula_id: int, db: Session = Depends(get_db)):
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    return (
        db.query(Horario)
        .filter(Horario.aula_id == aula_id)
        .order_by(Horario.dia_semana, Horario.hora_inicio)
        .all()
    )


@router.put("/horarios/{horario_id}", response_model=HorarioOut)
def mover_horario(horario_id: int, datos: HorarioUpdate, db: Session = Depends(get_db)):
    horario = db.query(Horario).filter(Horario.id == horario_id).first()
    if not horario:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    materia = db.query(Materia).filter(Materia.id == horario.materia_id).first()
    nueva_fin = time(hour=datos.hora_inicio.hour + 1)

    # Otros bloques que caen en la misma franja
    mismos = (
        db.query(Horario)
        .join(Materia, Horario.materia_id == Materia.id)
        .filter(
            Horario.id != horario_id,
            Horario.dia_semana == datos.dia_semana,
            Horario.hora_inicio == datos.hora_inicio,
        )
        .all()
    )
    for otro in mismos:
        if otro.aula_id == horario.aula_id:
            raise HTTPException(status_code=409, detail="El aula ya está ocupada en esa franja")
        if otro.materia.profesor_id == materia.profesor_id:
            raise HTTPException(status_code=409, detail="El profesor ya tiene clase en esa franja")
        if otro.materia.grupo_id == materia.grupo_id:
            raise HTTPException(status_code=409, detail="El grupo ya tiene clase en esa franja")

    horario.dia_semana = datos.dia_semana
    horario.hora_inicio = datos.hora_inicio
    horario.hora_fin = nueva_fin
    db.commit()
    db.refresh(horario)
    return horario


@router.delete("/horarios/{horario_id}")
def eliminar_horario(horario_id: int, db: Session = Depends(get_db)):
    horario = db.query(Horario).filter(Horario.id == horario_id).first()
    if not horario:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    db.delete(horario)
    db.commit()
    return {"mensaje": "Bloque de horario eliminado"}
