# Sistema de Optimización Automática de Horarios y Aulas — Backend

API REST que genera automáticamente horarios universitarios sin cruces de profesores, aulas ni grupos, resolviendo el problema como un **CSP (Constraint Satisfaction Problem)** con backtracking.

Proyecto final de Programación Orientada a la Web — Universidad Cooperativa de Colombia.

- **Frontend:** `<URL del repositorio del frontend>` (Angular, calendario con arrastrar y soltar)
- **API desplegada:** `<URL del backend en producción>`

## Tecnologías

- Python + FastAPI
- SQLAlchemy 2.0 + PostgreSQL (Supabase) con `psycopg` (v3)
- Pydantic v2 para validación
- pytest para pruebas

## Estructura

```
backend/
├── main.py              # App, CORS, logging y manejo de errores
├── database.py          # Conexión y sesión de base de datos
├── models.py            # Tablas (SQLAlchemy)
├── schemas.py           # Validación de entrada/salida (Pydantic)
├── routers/             # Endpoints agrupados por recurso (teachers, classrooms, schedules, ...)
├── services/
│   ├── csp.py           # Algoritmo de generación de horarios
│   ├── conflicts.py     # Detector de conflictos
│   ├── stats.py         # Ocupación, carga y cumplimiento
│   └── seed.py          # Datos de demostración
└── tests/               # Pruebas automatizadas
```

### Convención de idioma

- **Código en inglés:** clases, funciones, variables, archivos, comentarios y logs.
- **Español en lo que ve el usuario:** mensajes de error, textos de la documentación de `/docs`.
- **Contrato en español:** las URLs (`/profesores`), los campos JSON (`nombre`, `aforo`) y las tablas y columnas de la base de datos se mantienen en español para no romper el frontend ni migrar datos. Por eso un modelo en inglés conserva atributos como `Teacher.nombre`.

## Instalación y ejecución

```
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Crea un archivo `.env` (puedes copiar `.env.example`):

```
DATABASE_URL=postgresql+psycopg://usuario:contraseña@host:puerto/base
```

Inicia el servidor:

```
uvicorn main:app --reload
```

La documentación interactiva queda en `http://127.0.0.1:8000/docs`.

## Endpoints

| Recurso | Endpoints |
|---|---|
| Profesores | `POST /profesores`, `GET /profesores`, `PUT /profesores/{id}`, `DELETE /profesores/{id}` |
| Disponibilidad | `POST /disponibilidad`, `GET /disponibilidad/{profesor_id}`, `DELETE /disponibilidad/{id}` |
| Aulas | `POST /aulas`, `GET /aulas`, `PUT /aulas/{id}`, `DELETE /aulas/{id}` |
| Grupos | `POST /grupos`, `GET /grupos`, `PUT /grupos/{id}`, `DELETE /grupos/{id}` |
| Materias | `POST /materias`, `GET /materias`, `PUT /materias/{id}`, `DELETE /materias/{id}` |
| Horarios | `POST /generar-horario`, `GET /horarios`, `GET /horarios/grupo/{id}`, `GET /horarios/profesor/{id}`, `GET /horarios/aula/{id}`, `PUT /horarios/{id}`, `DELETE /horarios/{id}` |
| Análisis | `GET /conflictos`, `GET /estadisticas` |
| Utilidades | `POST /seed`, `GET /health` (verifica la conexión a la base de datos) |

### Códigos de error

Todos los errores responden `{"detail": "mensaje"}`:

- `404`: el recurso no existe.
- `409`: conflicto (correo o aula duplicados, borrar algo en uso, mover un bloque a una franja ocupada, o no hay horario posible).
- `422`: datos inválidos (correo mal formado, horas que no son en punto, rangos invertidos, etc.).
- `500`: error interno de base de datos.

## Cómo funciona el algoritmo

`POST /generar-horario` modela cada materia como un conjunto de bloques de 1 hora y busca una asignación `(día, hora, aula)` que cumpla estas restricciones:

1. El profesor solo da clase dentro de su disponibilidad.
2. Un profesor, un aula o un grupo no pueden estar en dos clases a la misma hora.
3. El aforo del aula debe ser mayor o igual al número de estudiantes del grupo.
4. Los bloques de una misma materia caen en días distintos.
5. Un grupo no tiene más de 4 horas de clase al día.

Técnicas aplicadas:

- **Backtracking completo:** si una materia posterior no tiene solución, se prueban otras combinaciones de las anteriores.
- **Heurística de grado y de restricción:** se asignan primero las materias con menos franjas disponibles por hora y las que comparten profesor o grupo con más materias.
- **Penalización de franjas muertas:** se prueban primero las franjas pegadas a otra clase del profesor o del grupo.
- **Límite de tiempo (10 s):** si no hay solución, responde `409` con un mensaje claro en lugar de bloquear el servidor.

## Datos de demostración

`POST /seed` carga 5 profesores ficticios, 4 aulas, 3 grupos y 7 materias (20 horas semanales). Si ya hay datos responde `409`; con `POST /seed?reiniciar=true` **borra todos los datos** y vuelve a cargar los de demostración. Después de cargarlos hay que llamar a `POST /generar-horario`.

## Pruebas

```
pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas usan una base SQLite temporal y nunca se conectan a la base de producción.

## Registro (logging)

Cada petición se registra con método, ruta, código y duración, además de la generación del horario y los errores de validación o de base de datos.
