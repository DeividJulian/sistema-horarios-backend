from sqlalchemy import Column, Integer, String, Time, ForeignKey
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
    # Role: "admin" (manages everything) or "usuario" (read-only: sees the schedule and the analysis)
    rol = Column(String, nullable=False, default="usuario", server_default="usuario")
