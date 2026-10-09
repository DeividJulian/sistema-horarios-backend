from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.orm import relationship

from database import Base


class Teacher(Base):
    __tablename__ = "profesores"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)

    availabilities = relationship("TeacherAvailability", back_populates="teacher", cascade="all, delete")


class TeacherAvailability(Base):
    __tablename__ = "disponibilidad_profesor"
    id = Column(Integer, primary_key=True, index=True)
    profesor_id = Column(Integer, ForeignKey("profesores.id"), nullable=False)
    dia_semana = Column(String, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)

    teacher = relationship("Teacher", back_populates="availabilities")


class Classroom(Base):
    __tablename__ = "aulas"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    aforo = Column(Integer, nullable=False)
    # Room type: "general", "informatica" (computer room) or "laboratorio"
    tipo = Column(String, nullable=False, default="general", server_default="general")


class StudentGroup(Base):
    __tablename__ = "grupos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    num_estudiantes = Column(Integer, nullable=False)
    # Shift the group studies in: "manana", "tarde", "noche" or "todo" (see SHIFTS in services/csp.py)
    jornada = Column(String, nullable=False, default="todo", server_default="todo")


class Subject(Base):
    __tablename__ = "materias"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    intensidad_horaria = Column(Integer, nullable=False)
    grupo_id = Column(Integer, ForeignKey("grupos.id"), nullable=False)
    profesor_id = Column(Integer, ForeignKey("profesores.id"), nullable=False)
    # Room type the subject needs: "cualquiera" (any), "informatica" or "laboratorio"
    tipo_aula = Column(String, nullable=False, default="cualquiera", server_default="cualquiera")

    group = relationship("StudentGroup")
    teacher = relationship("Teacher")


class ScheduleEntry(Base):
    __tablename__ = "horarios"
    id = Column(Integer, primary_key=True, index=True)
    materia_id = Column(Integer, ForeignKey("materias.id"), nullable=False)
    aula_id = Column(Integer, ForeignKey("aulas.id"), nullable=False)
    dia_semana = Column(String, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)

    subject = relationship("Subject")
    classroom = relationship("Classroom")


class User(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    # Role: "admin" (manages everything), "usuario" (read-only), "profesor" (sees and adjusts their own
    # classes) or "estudiante" (sees only their group's schedule)
    rol = Column(String, nullable=False, default="usuario", server_default="usuario")
    # Plain integer links (no foreign key) so they can be added to an existing table by migrations.py
    profesor_id = Column(Integer, nullable=True)  # profesor accounts: the teacher they belong to
    grupo_id = Column(Integer, nullable=True)  # estudiante accounts: the group they study in


class Cancellation(Base):
    """One class that will not take place on a given date (the weekly block itself stays)."""

    __tablename__ = "cancelaciones"
    id = Column(Integer, primary_key=True, index=True)
    horario_id = Column(Integer, ForeignKey("horarios.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha = Column(Date, nullable=False)
    motivo = Column(String, nullable=False)
    usuario_id = Column(Integer, nullable=True)
    creada_en = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    entry = relationship("ScheduleEntry")


class Notification(Base):
    """Notice for the students of a group (cancelled class, classroom change, schedule change)."""

    __tablename__ = "notificaciones"
    id = Column(Integer, primary_key=True, index=True)
    grupo_id = Column(Integer, nullable=False, index=True)
    materia_id = Column(Integer, nullable=True)
    horario_id = Column(Integer, nullable=True)
    # "cancelacion", "restablecida", "cambio_aula" or "cambio_horario"
    tipo = Column(String, nullable=False)
    titulo = Column(String, nullable=False)
    mensaje = Column(String, nullable=False)
    creada_en = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Backup(Base):
    """Copy of the academic data taken before the demo data replaced it, so it can be restored."""

    __tablename__ = "respaldos"
    id = Column(Integer, primary_key=True, index=True)
    creado_en = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # JSON: {"resumen": {...}, "tablas": {"profesores": [...], ...}, "usuarios": {...}}
    contenido = Column(Text, nullable=False)
