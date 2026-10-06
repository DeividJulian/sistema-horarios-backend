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
    assert "Ninguna aula sirve" in message and "aforo para 30 estudiantes" in message


def test_fails_if_not_enough_available_hours_and_explains_why(db):
    _scenario(db, weekly_hours=7)  # the teacher only has 6 available hours
    success, _, message = csp.compute_assignments(db)
    assert not success
    assert "6 h disponibles" in message and "necesita 7 h" in message


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


def _teacher_with_slot(db, name, day, start, end):
    teacher = Teacher(nombre=name, email=f"{name.lower()}@ucc.edu.co")
    db.add(teacher)
    db.flush()
    db.add(TeacherAvailability(profesor_id=teacher.id, dia_semana=day, hora_inicio=time(start), hora_fin=time(end)))
    return teacher


def _classroom_and_group(db, classrooms=1):
    db.add_all([Classroom(nombre=f"A{i + 1}", aforo=40) for i in range(classrooms)])
    db.add(StudentGroup(nombre="G1", num_estudiantes=30))
    db.flush()


def test_groups_hours_on_one_day_when_the_teacher_only_has_one(db):
    """Real case: Juan can only teach on Tuesday from 18 to 21 and has 3 weekly hours."""
    _classroom_and_group(db)
    juan = _teacher_with_slot(db, "Juan", "Martes", 18, 21)
    db.add(Subject(nombre="Programación Web", intensidad_horaria=3, grupo_id=1, profesor_id=juan.id))
    db.commit()
    success, assignments, _ = csp.compute_assignments(db)
    assert success
    assert [(d, h.hour) for _, _, d, h in assignments] == [("Martes", 18), ("Martes", 19), ("Martes", 20)]


def test_consecutive_hours_use_the_same_classroom(db):
    _classroom_and_group(db, classrooms=2)
    ana = _teacher_with_slot(db, "Ana", "Jueves", 8, 10)
    db.add(Subject(nombre="Bases de Datos", intensidad_horaria=2, grupo_id=1, profesor_id=ana.id))
    db.commit()
    success, assignments, _ = csp.compute_assignments(db)
    assert success and len({c.id for _, c, _, _ in assignments}) == 1


def test_prefers_spreading_over_different_days_when_possible(db):
    _scenario(db, weekly_hours=2)  # 3 available days: no need to group the hours
    success, assignments, _ = csp.compute_assignments(db)
    assert success and len({day for _, _, day, _ in assignments}) == 2


def test_two_teachers_with_different_slots_do_not_clash(db):
    """The schedule from the bug report: Juan on Tuesday evening and Deivid on Wednesday morning."""
    _classroom_and_group(db)
    juan = _teacher_with_slot(db, "Juan", "Martes", 18, 21)
    deivid = _teacher_with_slot(db, "Deivid", "Miércoles", 8, 10)
    db.add_all([
        Subject(nombre="Programación Web", intensidad_horaria=3, grupo_id=1, profesor_id=juan.id),
        Subject(nombre="Base de Datos", intensidad_horaria=2, grupo_id=1, profesor_id=deivid.id),
    ])
    db.commit()
    success, assignments, _ = csp.compute_assignments(db)
    assert success and len(assignments) == 5
    slots = {}
    for subject, _, day, hour in assignments:
        slots.setdefault(subject.nombre, set()).add((day, hour.hour))
    assert slots["Base de Datos"] == {("Miércoles", 8), ("Miércoles", 9)}
    assert slots["Programación Web"] == {("Martes", 18), ("Martes", 19), ("Martes", 20)}


def test_never_groups_more_hours_than_the_daily_group_maximum(db, monkeypatch):
    _classroom_and_group(db)
    juan = _teacher_with_slot(db, "Juan", "Martes", 14, 20)  # 6 hours on the same day
    db.add(Subject(nombre="Taller", intensidad_horaria=5, grupo_id=1, profesor_id=juan.id))
    db.commit()
    monkeypatch.setattr(csp, "MAX_GROUP_HOURS_PER_DAY", 4)
    success, _, _ = csp.compute_assignments(db)
    assert not success


def test_shortage_counts_every_subject_of_the_same_teacher(db):
    """3 available hours and two 2-hour subjects: each one fits alone, but not both."""
    _classroom_and_group(db)
    ana = _teacher_with_slot(db, "Ana", "Lunes", 8, 11)
    db.add_all([
        Subject(nombre="Redes", intensidad_horaria=2, grupo_id=1, profesor_id=ana.id),
        Subject(nombre="Sistemas", intensidad_horaria=2, grupo_id=1, profesor_id=ana.id),
    ])
    db.commit()
    success, _, message = csp.compute_assignments(db)
    assert not success
    assert "3 h disponibles" in message and "necesitan 4 h" in message
