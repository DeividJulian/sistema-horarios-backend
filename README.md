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
- Inicio de sesión sin contraseña: código de 6 dígitos por correo (Brevo) y sesión JWT (PyJWT)
- IA con Groq (gratis) por su endpoint compatible con OpenAI, sin SDK y con salidas estructuradas
- pytest para pruebas

## Estructura

```
backend/
├── main.py              # App, CORS, logging, manejo de errores y protección por rol
├── config.py            # Variables de entorno (sesión, códigos, correo, primer administrador)
├── security.py          # Tokens JWT y dependencias de autorización
├── database.py          # Conexión y sesión de base de datos
├── models.py            # Tablas (SQLAlchemy)
├── schemas.py           # Validación de entrada/salida (Pydantic)
├── routers/             # Endpoints agrupados por recurso (teachers, classrooms, schedules, ...)
├── services/
│   ├── csp.py           # Algoritmo de generación de horarios
│   ├── conflicts.py     # Detector de conflictos
│   ├── stats.py         # Ocupación, carga y cumplimiento
│   ├── seed.py          # Datos de demostración
│   ├── codes.py         # Códigos de 6 dígitos para entrar sin contraseña
│   ├── mailer.py        # Envío de correos (consola, memoria, SMTP o Brevo)
│   ├── llm.py           # Cliente de IA independiente del proveedor (Groq por defecto)
│   ├── privacy.py       # Quita nombres, correos y teléfonos antes de hablar con la IA
│   ├── ai.py            # Usos de la IA: resolver un conflicto y redactar avisos
│   └── users.py         # Primer administrador y una cuenta por profesor
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
SECRET_KEY=una-cadena-larga-y-aleatoria   # firma las sesiones y los códigos
EMAIL_BACKEND=consola                     # en local el código se ve en la terminal
ADMIN_EMAIL=tu-correo@gmail.com           # primer administrador
```

Con `EMAIL_BACKEND=consola` no se envía ningún correo: el código aparece en la terminal donde corre el servidor.

Inicia el servidor:

```
uvicorn main:app --reload
```

La documentación interactiva queda en `http://127.0.0.1:8000/docs`.

## Inicio de sesión y roles

Todos los endpoints de datos exigen iniciar sesión. **No hay contraseñas:** la persona escribe su correo, recibe un código de 6 dígitos y entra con él. El token se envía en la cabecera `Authorization: Bearer <token>` y dura `TOKEN_HORAS` (8 por defecto).

| Rol | Qué puede hacer |
|---|---|
| `admin` | Todo: crear, editar y eliminar datos, generar el horario, mover bloques, cargar datos de demostración y administrar usuarios. |
| `profesor` | Ver el horario y, en **sus propias clases**, cancelar una fecha (con motivo) o cambiar el aula. Cada cambio genera un aviso para el grupo. |
| `estudiante` | Ver solo el horario de **su grupo** (el backend filtra `GET /schedules`), sus cancelaciones y sus avisos. No accede al análisis de la facultad. |
| `usuario` | Consulta: ver todo sin modificar nada. |

### Código por correo

1. `POST /auth/login` con `{"email"}` envía el código (`404` si no hay cuenta con ese correo).
2. `POST /auth/verify` con `{"email", "codigo"}` devuelve el token y el usuario.

Reglas:
- Se genera con `secrets` y solo se guarda su HMAC-SHA256 (tabla `codigos_verificacion`).
- Vence en `CODIGO_MINUTOS` (10) y sirve una sola vez.
- Admite `CODIGO_INTENTOS` (5) intentos; después hay que pedir otro.
- Entre dos envíos hay que esperar `CODIGO_ESPERA_SEGUNDOS` (30): si no, responde `429` con la cabecera `Retry-After`.
- Un código nuevo anula los anteriores.
- Si el correo no sale, responde `502` y no se guarda nada; el log guarda el motivo que dio Brevo, sin la clave.
- Un token de una cuenta que nunca verificó su código recibe `401`.

**Envío de correos** con `EMAIL_BACKEND`:
- `consola`: local, se escribe en la terminal;
- `memoria`: pruebas;
- `smtp`: opcional;
- `brevo`: producción. Usa la API HTTP de Brevo, porque Render gratis bloquea SMTP, y necesita `BREVO_API_KEY` y un `EMAIL_FROM` verificado en Brevo.

### Cuentas

- **Administrador:** se crea al arrancar con `ADMIN_EMAIL` (y `ADMIN_NAME`) si no existe. Debe ser un correo real, porque ahí llega el código.
- **Profesores:** cada profesor entra con **el correo que tiene registrado**. Su cuenta se crea, actualiza o elimina sola cuando se crea, edita o elimina el profesor. Para probar varios profesores con un solo buzón sirve Gmail con `+algo` (`tucorreo+profe@gmail.com`).
- **Estudiantes:** se registran solos (ver abajo) o los crea un administrador.
- **Consulta y otros administradores:** los crea un administrador en Gestión → Usuarios, solo con nombre y correo.

Las cuentas que existían antes del login por código quedan verificadas. La migración agrega `usuarios.verificado` como `TRUE` para ellas, sin borrar nada. Las que tienen correos inventados no pueden recibir el código.

### Registro

`POST /auth/register` con nombre, correo y grupo crea la cuenta del **estudiante** sin verificar y le envía un código; `GET /auth/register-options` da la lista de grupos. Responde `409` si el correo ya está verificado o es de un profesor o del personal: ellos solo inician sesión. Nadie se registra como administrador.

## Endpoints

| Recurso | Endpoints | Acceso |
|---|---|---|
| Autenticación | `POST /auth/register`, `POST /auth/login`, `POST /auth/verify`, `GET /auth/register-options`, `GET /auth/me` | Público / con sesión |
| Usuarios | `GET /users`, `POST /users`, `PATCH /users/{id}/group`, `DELETE /users/{id}` | Administrador |
| Profesores | `POST /teachers`, `GET /teachers`, `PUT /teachers/{id}`, `DELETE /teachers/{id}` | Leer: con sesión · Cambiar: administrador |
| Disponibilidad | `POST /availability`, `GET /availability/{teacher_id}`, `DELETE /availability/{id}` | Igual |
| Aulas | `POST /classrooms`, `GET /classrooms`, `PUT /classrooms/{id}`, `DELETE /classrooms/{id}` | Igual |
| Grupos | `POST /groups`, `GET /groups`, `PUT /groups/{id}`, `DELETE /groups/{id}` | Igual |
| Materias | `POST /subjects`, `GET /subjects`, `PUT /subjects/{id}`, `DELETE /subjects/{id}` | Igual |
| Horarios | `POST /schedules/generate`, `GET /schedules`, `GET /schedules/group/{id}`, `GET /schedules/teacher/{id}`, `GET /schedules/classroom/{id}`, `PUT /schedules/{id}`, `DELETE /schedules/{id}` | Igual (el estudiante solo recibe su grupo) |
| Cambios de clase | `POST /schedules/{id}/cancellations`, `DELETE /cancellations/{id}`, `PATCH /schedules/{id}/classroom` | Profesor de esa clase o administrador |
| Cancelaciones y avisos | `GET /cancellations`, `GET /notifications` | Con sesión (cada rol ve lo suyo) |
| Análisis | `GET /conflicts`, `GET /statistics`, `GET /diagnostics` | Con sesión, excepto estudiantes |
| Inteligencia artificial | `GET /ai/status`, `POST /ai/conflicts/{id}/suggestion` (administrador), `POST /ai/notices/draft` (profesor de la clase o administrador) | Con sesión, excepto estudiantes |
| Datos de demostración | `POST /seed?dataset=demo\|faculty&reset=true`, `GET /seed/backup`, `POST /seed/restore`, `DELETE /seed/backup` | Administrador (leer la copia: con sesión) |
| Salud | `GET /health` | Público |

### Cancelaciones, cambios de aula y avisos

- **Cancelar** anula una clase en una fecha concreta (que debe caer en el día de la clase y no haber pasado); las demás semanas siguen igual. Se puede restablecer.
- **Cambiar de aula** es permanente y solo acepta aulas libres a esa hora, con aforo suficiente y del tipo que pide la materia.
- Cada cancelación, restablecimiento, cambio de aula o movimiento de un bloque crea un **aviso** (tabla `notificaciones`) para el grupo de la clase.

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

## Metaheurística: recocido simulado

Después de que el CSP encuentra un horario válido, `services/annealing.py` lo mejora con **recocido simulado**: mueve bloques completos (las horas seguidas de una materia en un día) a otro día, hora o aula y acepta los cambios que bajan el costo, y a veces los que lo suben, con una probabilidad que disminuye con la "temperatura", para salir de mínimos locales.

- **Costo:** horas muertas de grupos y profesores, más una penalización pequeña por días desbalanceados.
- **Restricciones:** cada movimiento respeta las mismas reglas duras del CSP, así que el resultado sigue sin cruces.
- **Determinista:** semilla fija, así que los mismos datos dan el mismo horario. Máximo 2,5 s, con parada temprana.
- `POST /schedules/generate` devuelve `optimizacion` con las horas muertas antes y después. En la facultad de prueba bajan de 104 a 22.

## Inteligencia artificial (Groq)

La IA **solo aconseja**: nunca cambia datos por su cuenta.

- **Resolver un conflicto** (`POST /ai/conflicts/{id}/suggestion`, administrador):
  - el sistema calcula hasta 6 franjas y aulas donde la clase en rojo cabe sin romper ninguna regla (disponibilidad, cruces, aforo, tipo de aula, jornada y máximo de horas por día);
  - el modelo elige la mejor y explica por qué;
  - el administrador la aplica con `PUT /schedules/{id}`, que ahora acepta `aula_id` opcional.
- **Redactar avisos** (`POST /ai/notices/draft`, profesor de la clase o administrador): a partir de un motivo breve, el modelo redacta el aviso para los estudiantes de una cancelación o un cambio de aula. El profesor lo revisa y lo envía en el campo opcional `aviso` de la cancelación o del cambio de aula; sin ese campo, el sistema escribe el aviso como antes.

**Privacidad:** al modelo nunca llegan nombres, correos ni teléfonos (`services/privacy.py`).
- Los profesores van como «Docente A, B…».
- Los correos y teléfonos del motivo se reemplazan.
- Los nombres reales vuelven solo en la respuesta que ve el usuario.

**Configuración:**
- Variables: `AI_PROVIDER` (`groq` por defecto; también `gemini` u `openai`), `AI_API_KEY` (la clave `gsk_…` de Groq), `AI_MODEL` (`openai/gpt-oss-20b`) y, opcionales, `AI_BASE_URL` y `AI_FALLBACK_MODEL`.
- Las respuestas usan salidas estructuradas (`json_schema` estricto) validadas con Pydantic.
- `GET /ai/status` responde `{configurada, proveedor, nombre_proveedor, modelo}`; el frontend muestra el proveedor que dice el servidor.

**Errores (nunca `500`):**
- sin clave: `503`;
- límite de uso: `429`, con `Retry-After` si el proveedor lo envía;
- proveedor caído, lento o con una respuesta inválida: `502`. Se reintenta una vez si responde `5xx`.

Las pruebas simulan el HTTP de Groq, así que nunca llaman a la API real.

## Datos de demostración

`POST /seed` carga 5 profesores ficticios, 4 aulas, 3 grupos y 7 materias (20 horas semanales). Si ya hay datos responde `409`; con `POST /seed?reset=true` reemplaza los datos por los de demostración, **pero antes guarda una copia** (tabla `respaldos`) de profesores, disponibilidad, aulas, grupos, materias, horario, cancelaciones, avisos y cuentas de profesor. `POST /seed/restore` vuelve exactamente a esos datos (con los mismos ids, así los estudiantes siguen en su grupo) y `DELETE /seed/backup` descarta la copia. Solo se guarda la primera copia: cargar la demo otra vez no la sobrescribe. Con `?dataset=faculty` carga una facultad completa de 8 semestres. Después de cargarlos hay que llamar a `POST /schedules/generate`.

## Pruebas

```
pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas usan una base SQLite temporal y nunca se conectan a la base de producción.

## Registro (logging)

Cada petición se registra con método, ruta, código y duración, además de la generación del horario y los errores de validación o de base de datos.
