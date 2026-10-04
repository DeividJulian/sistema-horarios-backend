from datetime import time

from models import Classroom, TeacherAvailability, StudentGroup, Subject, Teacher
from services import csp


def _escenario(db, aforo_aula=40, estudiantes=30, intensidad=3):
    classroom = Classroom(nombre="A1", aforo=aforo_aula)
    group = StudentGroup(nombre="G1", num_estudiantes=estudiantes)
    prof = Teacher(nombre="Prof", email="prof@ucc.edu.co")
    db.add_all([classroom, group, prof])
    db.flush()
    for dia in ["Lunes", "Martes", "Miércoles"]:
        db.add(TeacherAvailability(profesor_id=prof.id, dia_semana=dia, hora_inicio=time(8), hora_fin=time(10)))
    db.add(Subject(nombre="M1", intensidad_horaria=intensidad, grupo_id=group.id, profesor_id=prof.id))
    db.commit()


def test_asigna_dias_distintos_a_una_materia(db):
    _escenario(db)
    exito, asignaciones, _ = csp.compute_assignments(db)
    assert exito
    dias = [dia for _, _, dia, _ in asignaciones]
    assert len(dias) == len(set(dias)) == 3


def test_falla_si_el_aula_no_tiene_aforo(db):
    _escenario(db, aforo_aula=10, estudiantes=30)
    exito, asignaciones, mensaje = csp.compute_assignments(db)
    assert not exito and asignaciones == []
    assert "No fue posible" in mensaje


def test_falla_si_faltan_dias_disponibles(db):
    _escenario(db, intensidad=5)  # el profesor solo tiene 3 días
    exito, _, _ = csp.compute_assignments(db)
    assert not exito


def test_limite_de_tiempo_devuelve_mensaje(db, monkeypatch):
    _escenario(db)
    monkeypatch.setattr(csp, "TIME_LIMIT_SECONDS", 0)
    exito, _, mensaje = csp.compute_assignments(db)
    assert not exito
    assert "límite" in mensaje


def test_respeta_maximo_de_horas_diarias_por_grupo(db, monkeypatch):
    _escenario(db)
    monkeypatch.setattr(csp, "MAX_GROUP_HOURS_PER_DAY", 0)
    exito, _, _ = csp.compute_assignments(db)
    assert not exito
