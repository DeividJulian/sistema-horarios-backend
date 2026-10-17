"""
Metaheuristic phase: simulated annealing over a valid schedule.

The CSP (services/csp.py) finds a schedule without clashes; this phase then improves it. It repeatedly moves one
block (the consecutive hours of a subject on one day) to another day, hour or classroom and keeps the change when it
lowers the cost. Worse changes are also accepted with a probability that decreases over time (the "temperature"),
which lets the search escape local minima.

Every move is checked against the hard constraints, so the result is always as valid as the CSP's:
teacher availability inside the group's shift, no teacher/classroom/group clashes, classroom capacity and type,
at most MAX_GROUP_HOURS_PER_DAY hours per group and day, and one block per subject and day.

Cost to minimise: idle hours (gaps between two classes of the same day) of groups and teachers, plus a small
penalty for unbalanced days of a group.
"""
import math
import random
import time as clock
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import time

TIME_BUDGET_SECONDS = 2.5
INITIAL_TEMPERATURE = 2.0
COOLING = 0.995
STEPS_PER_TEMPERATURE = 40
MIN_TEMPERATURE = 0.01
IMBALANCE_WEIGHT = 0.1
# Stop early when nothing improved for this many moves (small schedules finish in milliseconds)
PATIENCE = 4000


@dataclass
class Block:
    subject: object
    classroom: object
    day: str
    start: int  # first hour (0-23)
    length: int

    def hours(self):
        return range(self.start, self.start + self.length)


@dataclass
class AnnealingStats:
    idle_before: int = 0
    idle_after: int = 0
    cost_before: float = 0.0
    cost_after: float = 0.0
    iterations: int = 0
    accepted: int = 0
    improvements: int = 0
    seconds: float = 0.0
    details: dict = field(default_factory=dict)


def _idle_hours(hours: list[int]) -> int:
    """Free hours between the first and the last class of a day."""
    return (max(hours) - min(hours) + 1 - len(hours)) if hours else 0


class _State:
    """Occupancy of the schedule, so a move can be checked and scored without rebuilding everything."""

    def __init__(self, blocks: list[Block]):
        self.blocks = blocks
        self.teacher = defaultdict(set)  # (teacher, day) -> hours
        self.group = defaultdict(set)  # (group, day) -> hours
        self.classroom = defaultdict(set)  # (classroom, day) -> hours
        self.subject_days = defaultdict(set)  # subject -> days with a block
        for block in blocks:
            self._add(block)

    def _add(self, block: Block):
        s = block.subject
        for h in block.hours():
            self.teacher[(s.profesor_id, block.day)].add(h)
            self.group[(s.grupo_id, block.day)].add(h)
            self.classroom[(block.classroom.id, block.day)].add(h)
        self.subject_days[s.id].add(block.day)

    def _remove(self, block: Block):
        s = block.subject
        for h in block.hours():
            self.teacher[(s.profesor_id, block.day)].discard(h)
            self.group[(s.grupo_id, block.day)].discard(h)
            self.classroom[(block.classroom.id, block.day)].discard(h)
        self.subject_days[s.id].discard(block.day)

    def entity_cost(self, group_id: int, teacher_id: int, day: str) -> float:
        return _idle_hours(sorted(self.group[(group_id, day)])) + _idle_hours(sorted(self.teacher[(teacher_id, day)]))

    def group_imbalance(self, group_id: int, days: list[str]) -> float:
        loads = [len(self.group[(group_id, d)]) for d in days]
        return max(loads) - min(loads) if loads else 0

    def total_cost(self, days: list[str]) -> float:
        idle = sum(_idle_hours(sorted(h)) for h in self.group.values()) + sum(_idle_hours(sorted(h)) for h in self.teacher.values())
        groups = {b.subject.grupo_id for b in self.blocks}
        return idle + IMBALANCE_WEIGHT * sum(self.group_imbalance(g, days) for g in groups)

    def total_idle(self) -> int:
        return sum(_idle_hours(sorted(h)) for h in self.group.values()) + sum(_idle_hours(sorted(h)) for h in self.teacher.values())


def _to_blocks(assignments) -> list[Block]:
    """Joins the 1-hour assignments of the CSP into blocks (consecutive hours of a subject on one day)."""
    by_subject_day = defaultdict(list)
    order = []
    for subject, classroom, day, hour in assignments:
        key = (subject.id, day)
        if key not in by_subject_day:
            order.append(key)
        by_subject_day[key].append((subject, classroom, hour.hour))
    blocks = []
    for key in order:
        items = sorted(by_subject_day[key], key=lambda x: x[2])
        subject, classroom, start = items[0]
        blocks.append(Block(subject, classroom, key[1], start, len(items)))
    return blocks


def _to_assignments(blocks: list[Block]):
    return [(b.subject, b.classroom, b.day, time(hour=h)) for b in blocks for h in b.hours()]


def improve_schedule(assignments, usable_slots, classrooms, groups, max_group_hours: int, classroom_fits, weekdays, seed: int = 7):
    """
    Returns (improved assignments, AnnealingStats). `usable_slots(subject)` gives the (day, time) slots where the
    subject may be taught; `classroom_fits(classroom, subject, students)` checks capacity and type.
    """
    started = clock.monotonic()
    rng = random.Random(seed)  # fixed seed: the same data always gives the same schedule
    blocks = _to_blocks(assignments)
    state = _State(blocks)
    stats = AnnealingStats()
    stats.idle_before = state.total_idle()
    stats.cost_before = current_cost = state.total_cost(weekdays)
    if not blocks:
        return assignments, stats

    # Possible placements of each block, computed once: (day, start, classroom) where its teacher is available
    # for every hour and the classroom fits the subject.
    options = {}
    for i, block in enumerate(blocks):
        subject = block.subject
        group = groups.get(subject.grupo_id)
        slots = {(d, h.hour) for d, h in usable_slots(subject)}
        rooms = [c for c in classrooms if group and classroom_fits(c, subject, group.num_estudiantes)]
        options[i] = [
            (day, start, room)
            for day in weekdays
            for start in range(0, 24)
            if all((day, start + k) in slots for k in range(block.length))
            for room in rooms
        ]

    def fits(block: Block, day: str, start: int, room) -> bool:
        s = block.subject
        hours = range(start, start + block.length)
        if day != block.day and day in state.subject_days[s.id]:
            return False  # one block per subject and day
        if len(state.group[(s.grupo_id, day)]) + block.length > max_group_hours:
            return False
        return not any(
            h in state.teacher[(s.profesor_id, day)] or h in state.group[(s.grupo_id, day)] or h in state.classroom[(room.id, day)]
            for h in hours
        )

    best = [Block(b.subject, b.classroom, b.day, b.start, b.length) for b in blocks]
    best_cost = current_cost
    temperature = INITIAL_TEMPERATURE
    last_improvement = 0

    while (
        clock.monotonic() - started < TIME_BUDGET_SECONDS
        and temperature > MIN_TEMPERATURE
        and best_cost > 1e-9  # nothing left to improve
        and stats.iterations - last_improvement < PATIENCE
    ):
        for _ in range(STEPS_PER_TEMPERATURE):
            stats.iterations += 1
            i = rng.randrange(len(blocks))
            if not options[i]:
                continue
            block = blocks[i]
            day, start, room = rng.choice(options[i])
            if (day, start, room.id) == (block.day, block.start, block.classroom.id):
                continue

            s = block.subject
            old = (block.day, block.start, block.classroom)
            affected_days = {block.day, day}
            before = sum(state.entity_cost(s.grupo_id, s.profesor_id, d) for d in affected_days)
            before += IMBALANCE_WEIGHT * state.group_imbalance(s.grupo_id, weekdays)

            state._remove(block)
            if not fits(block, day, start, room):
                state._add(block)
                continue
            block.day, block.start, block.classroom = day, start, room
            state._add(block)

            after = sum(state.entity_cost(s.grupo_id, s.profesor_id, d) for d in affected_days)
            after += IMBALANCE_WEIGHT * state.group_imbalance(s.grupo_id, weekdays)
            delta = after - before

            if delta <= 0 or rng.random() < math.exp(-delta / temperature):
                stats.accepted += 1
                current_cost += delta
                if current_cost < best_cost - 1e-9:
                    stats.improvements += 1
                    last_improvement = stats.iterations
                    best_cost = current_cost
                    best = [Block(b.subject, b.classroom, b.day, b.start, b.length) for b in blocks]
            else:
                state._remove(block)
                block.day, block.start, block.classroom = old
                state._add(block)
        temperature *= COOLING

    final_state = _State(best)
    stats.idle_after = final_state.total_idle()
    stats.cost_after = final_state.total_cost(weekdays)
    stats.seconds = round(clock.monotonic() - started, 2)
    return _to_assignments(best), stats
