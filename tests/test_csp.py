from datetime import time

from models import Classroom, TeacherAvailability, StudentGroup, Subject, Teacher
from services import csp


def _scenario(db, classroom_capacity=40, students=30, weekly_hours=3):
    classroom = Classroom(nombre="A1", aforo=classroom_capacity)
    group = StudentGroup(nombre="G1", num_estudiantes=students)
    teacher = Teacher(nombre="Prof", email="prof@ucc.edu.co")
    db.add_all([classroom, group, teacher])
    db.flush()
    for day in ["Lunes", "Martes", "Miércoles"]:
        db.add(TeacherAvailability(profesor_id=teacher.id, dia_semana=day, hora_inicio=time(8), hora_fin=time(10)))
    db.add(Subject(nombre="M1", intensidad_horaria=weekly_hours, grupo_id=group.id, profesor_id=teacher.id))
    db.commit()


def test_assigns_different_days_to_a_subject(db):
    _scenario(db)
    success, assignments, _ = csp.compute_assignments(db)
    assert success
    days = [day for _, _, day, _ in assignments]
    assert len(days) == len(set(days)) == 3


def test_fails_if_classroom_is_too_small(db):
    _scenario(db, classroom_capacity=10, students=30)
    success, assignments, message = csp.compute_assignments(db)
    assert not success and assignments == []
    assert "No fue posible" in message


def test_fails_if_not_enough_available_days(db):
    _scenario(db, weekly_hours=5)  # the teacher only has 3 days
    success, _, _ = csp.compute_assignments(db)
    assert not success


def test_time_limit_returns_message(db, monkeypatch):
    _scenario(db)
    monkeypatch.setattr(csp, "TIME_LIMIT_SECONDS", 0)
    success, _, message = csp.compute_assignments(db)
    assert not success
    assert "límite" in message


def test_respects_max_daily_hours_per_group(db, monkeypatch):
    _scenario(db)
    monkeypatch.setattr(csp, "MAX_GROUP_HOURS_PER_DAY", 0)
    success, _, _ = csp.compute_assignments(db)
    assert not success
