from collections import defaultdict
from datetime import time
from types import SimpleNamespace

from models import Classroom, StudentGroup, Subject, TeacherAvailability
from services import csp
from services.annealing import improve_schedule
from services.seed import load_demo_data, load_faculty_data


def _hard_constraint_problems(db, assignments):
    """Every rule the CSP guarantees, checked again on the final schedule."""
    groups = {g.id: g for g in db.query(StudentGroup).all()}
    availability = defaultdict(set)
    for a in db.query(TeacherAvailability).all():
        for h in range(a.hora_inicio.hour, a.hora_fin.hour):
            availability[a.profesor_id].add((a.dia_semana, h))
    problems = []
    seen_teacher, seen_group, seen_room = set(), set(), set()
    per_group_day = defaultdict(int)
    per_subject_day = defaultdict(list)
    for subject, room, day, hour in assignments:
        h = hour.hour
        group = groups[subject.grupo_id]
        start, end = csp.shift_range(group.jornada)
        if (day, h) not in availability[subject.profesor_id] or not start <= h < end:
            problems.append(f"{subject.nombre} fuera de disponibilidad o jornada")
        if not csp.classroom_fits(room, subject, group.num_estudiantes):
            problems.append(f"{subject.nombre} en un aula que no sirve")
        for seen, key in ((seen_teacher, subject.profesor_id), (seen_group, subject.grupo_id), (seen_room, room.id)):
            if (key, day, h) in seen:
                problems.append(f"cruce en {day} {h}")
            seen.add((key, day, h))
        per_group_day[(subject.grupo_id, day)] += 1
        per_subject_day[(subject.id, day)].append((h, room.id))
    problems += [f"grupo {g} con {n} h el {d}" for (g, d), n in per_group_day.items() if n > csp.MAX_GROUP_HOURS_PER_DAY]
    for (subject_id, day), items in per_subject_day.items():
        hours = sorted(h for h, _ in items)
        if hours != list(range(hours[0], hours[0] + len(hours))) or len({r for _, r in items}) > 1:
            problems.append(f"materia {subject_id} partida el {day}")
    return problems


def test_annealing_closes_idle_gaps():
    """Two 1-hour classes of the same group at 8 and 11: the gap of 2 hours disappears."""
    group = SimpleNamespace(id=1, num_estudiantes=20)
    room = SimpleNamespace(id=1, aforo=30, tipo="general")
    a = SimpleNamespace(id=1, grupo_id=1, profesor_id=1, tipo_aula="cualquiera")
    b = SimpleNamespace(id=2, grupo_id=1, profesor_id=2, tipo_aula="cualquiera")
    assignments = [(a, room, "Lunes", time(8)), (b, room, "Lunes", time(11))]
    slots = {("Lunes", time(h)) for h in range(8, 12)}

    improved, stats = improve_schedule(
        assignments, lambda s: slots, [room], {1: group}, 4, csp.classroom_fits, csp.WEEKDAYS
    )
    assert stats.idle_before == 2 and stats.idle_after == 0
    hours = sorted(h.hour for _, _, _, h in improved)
    assert hours[1] - hours[0] == 1  # now back to back


def test_annealing_keeps_every_hard_constraint_on_the_faculty(db):
    load_faculty_data(db)
    stats = {}
    success, assignments, _ = csp.compute_assignments(db, stats=stats)
    assert success
    assert _hard_constraint_problems(db, assignments) == []
    total = sum(s.intensidad_horaria for s in db.query(Subject).all())
    assert len(assignments) == total
    assert stats["horas_muertas_despues"] <= stats["horas_muertas_antes"]
    assert stats["iteraciones"] > 0


def test_annealing_never_makes_the_demo_worse(db):
    load_demo_data(db)
    _, plain, _ = csp.compute_assignments(db, improve=False)
    stats = {}
    _, improved, _ = csp.compute_assignments(db, stats=stats)
    assert _hard_constraint_problems(db, improved) == []
    assert stats["horas_muertas_despues"] <= stats["horas_muertas_antes"]
    assert len(improved) == len(plain)


def test_same_data_gives_the_same_schedule(db):
    load_demo_data(db)
    _, first, _ = csp.compute_assignments(db)
    _, second, _ = csp.compute_assignments(db)
    key = lambda items: sorted((s.id, r.id, d, h.hour) for s, r, d, h in items)
    assert key(first) == key(second)


def test_generate_endpoint_reports_the_optimization(client, demo_data):
    body = client.post("/schedules/generate").json()
    opt = body["optimizacion"]
    assert set(opt) >= {"horas_muertas_antes", "horas_muertas_despues", "iteraciones", "mejoras", "segundos"}
    assert opt["horas_muertas_despues"] <= opt["horas_muertas_antes"]
