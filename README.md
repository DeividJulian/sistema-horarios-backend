# Sistema de Optimización Automática de Horarios y Aulas — Backend

API REST que genera automáticamente horarios universitarios sin cruces de profesores, aulas ni grupos, resolviendo el problema como un **CSP (Constraint Satisfaction Problem)** con backtracking.

Proyecto final de Programación Orientada a la Web — Universidad Cooperativa de Colombia.

- **Frontend:** https://github.com/DeividJulian/sistema-horarios-frontend (Angular, calendario con arrastrar y soltar)
- **API desplegada:** https://sistema-horarios-backend.onrender.com (documentación en `/docs`)
- **Aplicación web:** https://sistema-horarios-frontend.vercel.app

## Tecnologías

- Python + FastAPI
- SQLAlchemy 2.0 + PostgreSQL (Supabase) con `psycopg` (v3)
- Pydantic v2 para validación
- JWT (PyJWT) para el inicio de sesión y contraseñas cifradas con PBKDF2-SHA256
- pytest para pruebas

## Estructura

```
backend/
├── main.py              # App, CORS, logging, manejo de errores y protección por rol
├── security.py          # Contraseñas, tokens JWT y dependencias de autorización
├── database.py          # Conexión y sesión de base de datos
├── models.py            # Tablas (SQLAlchemy)
├── schemas.py           # Validación de entrada/salida (Pydantic)
├── routers/             # Endpoints agrupados por recurso (teachers, classrooms, schedules, ...)
├── services/
│   ├── csp.py           # Algoritmo de generación de horarios
│   ├── conflicts.py     # Detector de conflictos
│   ├── stats.py         # Ocupación, carga y cumplimiento
│   ├── seed.py          # Datos de demostración
│   └── users.py         # Cuentas creadas al iniciar por primera vez
└── tests/               # Pruebas automatizadas
```

### Convención de idioma

- **Código en inglés:** clases, funciones, variables, archivos, comentarios y logs.
- **Español en lo que ve el usuario:** mensajes de error, textos de la documentación de `/docs`.
- **Endpoints en inglés:** `/teachers`, `/classrooms`, `/schedules/generate`, etc.
- **Datos en español:** los campos JSON (`nombre`, `aforo`) y las tablas y columnas de la base de datos se mantienen en español para no migrar los datos existentes. Por eso un modelo en inglés conserva atributos como `Teacher.nombre`.

## Instalación y ejecución

```
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Crea un archivo `.env` (puedes copiar `.env.example`):

```
DATABASE_URL=postgresql+psycopg://usuario:contraseña@host:puerto/base
JWT_SECRET=una-cadena-larga-y-aleatoria   # opcional, recomendado en producción
```

Inicia el servidor:

```
uvicorn main:app --reload
```

La documentación interactiva queda en `http://127.0.0.1:8000/docs`.

## Inicio de sesión y roles

Todos los endpoints de datos exigen iniciar sesión. El token se envía en la cabecera `Authorization: Bearer <token>` y dura 8 horas.

| Rol | Qué puede hacer |
|---|---|
| `admin` | Todo: crear, editar y eliminar datos, generar el horario, cargar datos de demostración y administrar usuarios. |
| `usuario` | Solo consultar: ver el horario, los filtros y el análisis. Cualquier cambio responde `403`. |

La primera vez que arranca con la tabla `usuarios` vacía, el servidor crea dos cuentas de prueba:

| Rol | Correo | Contraseña |
|---|---|---|
| Administrador | `admin@horarios.edu.co` | `Admin2026*` |
| Usuario | `usuario@horarios.edu.co` | `Usuario2026*` |

Se pueden cambiar con las variables de entorno `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `USER_EMAIL` y `USER_PASSWORD`, o creando otros usuarios desde la aplicación.

## Endpoints

| Recurso | Endpoints | Acceso |
|---|---|---|
| Autenticación | `POST /auth/login`, `GET /auth/me` | Público / con sesión |
| Usuarios | `GET /users`, `POST /users`, `DELETE /users/{id}` | Administrador |
| Profesores | `POST /teachers`, `GET /teachers`, `PUT /teachers/{id}`, `DELETE /teachers/{id}` | Leer: con sesión · Cambiar: administrador |
| Disponibilidad | `POST /availability`, `GET /availability/{teacher_id}`, `DELETE /availability/{id}` | Igual |
| Aulas | `POST /classrooms`, `GET /classrooms`, `PUT /classrooms/{id}`, `DELETE /classrooms/{id}` | Igual |
| Grupos | `POST /groups`, `GET /groups`, `PUT /groups/{id}`, `DELETE /groups/{id}` | Igual |
| Materias | `POST /subjects`, `GET /subjects`, `PUT /subjects/{id}`, `DELETE /subjects/{id}` | Igual |
| Horarios | `POST /schedules/generate`, `GET /schedules`, `GET /schedules/group/{id}`, `GET /schedules/teacher/{id}`, `GET /schedules/classroom/{id}`, `PUT /schedules/{id}`, `DELETE /schedules/{id}` | Igual |
| Análisis | `GET /conflicts`, `GET /statistics`, `GET /diagnostics` | Con sesión |
| Utilidades | `POST /seed?dataset=demo\|faculty&reset=true` (administrador), `GET /health` (público) | |

### Códigos de error

Todos los errores responden `{"detail": "mensaje"}`:

- `401`: no hay sesión o el token expiró.
- `403`: el rol no permite la acción (por ejemplo, un usuario de consulta intentando editar).
- `404`: el recurso no existe.
- `409`: conflicto (correo o aula duplicados, borrar algo en uso, mover un bloque a una franja ocupada, o no hay horario posible).
- `422`: datos inválidos (correo mal formado, horas que no son en punto, rangos invertidos, etc.).
- `500`: error interno de base de datos.

## Cómo funciona el algoritmo

`POST /schedules/generate` modela cada materia como un conjunto de bloques de 1 hora y busca una asignación `(día, hora, aula)` que cumpla estas restricciones:

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

`POST /seed` carga 5 profesores ficticios, 4 aulas, 3 grupos y 7 materias (20 horas semanales). Si ya hay datos responde `409`; con `POST /seed?reset=true` **borra todos los datos** (menos los usuarios) y vuelve a cargar los de demostración. Con `?dataset=faculty` carga una facultad completa de 8 semestres. Después de cargarlos hay que llamar a `POST /schedules/generate`.

## Pruebas

```
pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas usan una base SQLite temporal y nunca se conectan a la base de producción.

## Registro (logging)

Cada petición se registra con método, ruta, código y duración, además de la generación del horario y los errores de validación o de base de datos.
