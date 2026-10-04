from sqlalchemy import Column, Integer, String, Time, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


class Profesor(Base):
    __tablename__ = "profesores"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)

    disponibilidades = relationship("DisponibilidadProfesor", back_populates="profesor", cascade="all, delete")


class DisponibilidadProfesor(Base):
    __tablename__ = "disponibilidad_profesor"
    id = Column(Integer, primary_key=True, index=True)
    profesor_id = Column(Integer, ForeignKey("profesores.id"), nullable=False)
    dia_semana = Column(String, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)

    profesor = relationship("Profesor", back_populates="disponibilidades")


class Aula(Base):
    __tablename__ = "aulas"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    aforo = Column(Integer, nullable=False)


class Grupo(Base):
    __tablename__ = "grupos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    num_estudiantes = Column(Integer, nullable=False)


class Materia(Base):
    __tablename__ = "materias"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    intensidad_horaria = Column(Integer, nullable=False)
    grupo_id = Column(Integer, ForeignKey("grupos.id"), nullable=False)
    profesor_id = Column(Integer, ForeignKey("profesores.id"), nullable=False)

    grupo = relationship("Grupo")
    profesor = relationship("Profesor")


class Horario(Base):
    __tablename__ = "horarios"
    id = Column(Integer, primary_key=True, index=True)
    materia_id = Column(Integer, ForeignKey("materias.id"), nullable=False)
    aula_id = Column(Integer, ForeignKey("aulas.id"), nullable=False)
    dia_semana = Column(String, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)

    materia = relationship("Materia")
    aula = relationship("Aula")
