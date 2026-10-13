# Sistema de Votaciones (SIVOTES)

Proyecto Django para la gestión de procesos electorales, validación de votantes,
flujo de kiosco, panel de participación, auditoría de padrón y cierre del proceso
con acta oficial en PDF.

---

## Descripción general

Este proyecto está organizado como una aplicación Django modular con varios
módulos funcionales:

- `apps/voters/`: gestión de electores, padrones, validación y procesos electorales.
- `apps/voting/`: flujo electoral, kiosco, dashboard, cierre del proceso y acta.
- `apps/candidates/`: tipos de elección, listas y fotos de candidatura.
- `apps/auditoria/`: registro de acciones administrativas.
- `apps/core/`: utilidades transversales, criptografía y hashing.
- `config/`: configuración del proyecto y URLs principales.

---

## Requisitos

- Python 3.11+ (idealmente 3.13 según entorno usado)
- pip
- virtualenv o venv
- SQLite por defecto (`db.sqlite3`)
- Pillow (para subir imágenes)
- xhtml2pdf (para generar el acta en PDF)

---

## 🐳 Despliegue con Docker

El proyecto incluye un `Dockerfile`, un `docker-compose.yml` y un `entrypoint.sh`
listos para correr la aplicación en producción con **SQLite** dentro del contenedor.

> ⚠️ El archivo `db.sqlite3` del host **no se copia** a la imagen gracias a
> `.dockerignore`. La base de datos se crea limpia dentro del contenedor en el
> volumen `dbdata`.

### 1. Requisitos

- Docker 24+
- Docker Compose v2 (`docker compose`)

### 2. Preparar las variables de entorno

Copia la plantilla y completa los valores sensibles:

```bash
cp .env.example .env
```

Edita `.env` y reemplaza al menos:

- `SECRET_KEY` — clave aleatoria larga y segura.
- `HASH_SALT` — salt para el hash de participación.
- `VOTE_KEY` — clave Fernet para cifrar boletas (`cryptography.fernet.Fernet.generate_key()`).

Genera claves con:

```bash
python -c "from cryptography.fernet import Fernet; print('VOTE_KEY=' + Fernet.generate_key().decode())"
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(50))"
```

La variable `DATABASE_URL` apunta por defecto a `sqlite:////app/data/db.sqlite3`
dentro del contenedor (no hace falta cambiarla).

### 3. Construir y levantar

```bash
docker compose up --build
```

La primera vez:

1. Instala los requisitos de Python (`requirements/base.txt`).
2. Espera a la base de datos.
3. Aplica las migraciones (`migrate --noinput`).
4. Recolecta archivos estáticos (`collectstatic --noinput`).
5. Arranca **Gunicorn** en `0.0.0.0:8000` con 3 workers.

Para correr en segundo plano:

```bash
docker compose up --build -d
```

### 4. Acceder a la aplicación

- Web: [http://localhost:8000](http://localhost:8000)
- Admin: [http://localhost:8000/admin/](http://localhost:8000/admin/)

### 5. Crear el superusuario

El `entrypoint.sh` ya ejecutó `migrate`, pero no crea un usuario. Créalo dentro
del contenedor:

```bash
docker compose exec web python manage.py createsuperuser
```

### 5. Cargar datos demo automáticamente

El `entrypoint.sh` puede invocar `python manage.py seed_demo` justo después de
las migraciones si activas la variable `LOAD_DEMO_DATA=true` en tu `.env`:

```env
LOAD_DEMO_DATA=true
LOAD_DEMO_RESET=false          # true para borrar el proceso demo antes
LOAD_DEMO_ADMIN_USER=admin
LOAD_DEMO_ADMIN_PASS=admin
LOAD_DEMO_ADMIN_EMAIL=admin@example.com
```

> El primer arranque será más lento porque crea el superusuario, 1 proceso
> activo, 2 mesas, 2 tipos de elección, 4 listas y 4 estudiantes de prueba.

Una vez cargados los datos:

| Recurso | URL | Credenciales |
|--------|-----|--------------|
| Admin  | `http://localhost:8000/admin/` | `admin` / `admin` |
| Panel  | `http://localhost:8000/panel/` | sesión de admin |
| Kiosco | `http://localhost:8000/` | DNIs: `42822315` … `42822318` |

Para volver a cargar datos limpios desde cero:

```bash
docker compose down -v          # borra BD y volúmenes
# editar .env: LOAD_DEMO_RESET=true
docker compose up --build
```

### 6. Comandos frecuentes

```bash
# Ver logs en vivo
docker compose logs -f web

# Ejecutar comandos de Django dentro del contenedor
docker compose exec web python manage.py shell
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py loaddata fixtures/demo.json

# Abrir una shell de bash
docker compose exec web bash

# Detener y eliminar contenedores (conserva volúmenes)
docker compose down

# Detener y eliminar contenedores + volúmenes (BORRA LA BD)
docker compose down -v
```

### 7. Volúmenes persistentes

| Volumen       | Ruta en el contenedor | Descripción                          |
|---------------|----------------------|--------------------------------------|
| `staticfiles` | `/app/staticfiles`   | Archivos estáticos recolectados.      |
| `media`       | `/app/media`         | Archivos subidos por usuarios.       |
| `dbdata`      | `/app/data`          | `db.sqlite3` (persiste entre reinicios). |

Si prefieres inspeccionar la base de datos SQLite:

```bash
docker compose exec web sqlite3 /app/data/db.sqlite3 ".tables"
```

### 8. Construcción de la imagen sin Compose

Si solo quieres construir la imagen y correrla manualmente:

```bash
docker build -t proy-cole-votaciones .
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v staticfiles:/app/staticfiles \
  -v media:/app/media \
  -v dbdata:/app/data \
  proy-cole-votaciones
```

---

## Clonar y preparar entorno

Desde la carpeta del proyecto:

```bash
cd proy_cole_votaciones
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements/base.txt
```

Si el entorno ya existe, solo activa el virtualenv:

```bash
cd proy_cole_votaciones
source venv/bin/activate
```

---

## Variables de entorno / configuración

El proyecto usa configuración por ambiente desde `config/settings/`.

Por defecto, el entorno de desarrollo suele apuntar a:

```bash
config/settings/development.py
```

Asegúrate de revisar la configuración antes de ejecutar por primera vez:

- `SECRET_KEY`
- `VOTE_KEY` (Fernet, para cifrar boletas)
- `HASH_SALT` (para el hash de participación)
- `DATABASE_URL`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`

Estos valores se leen desde un archivo `.env` en la raíz del proyecto.

---

## Migraciones

Aplicar migraciones iniciales:

```bash
python manage.py migrate
```

Si agregas nuevos modelos o cambios de esquema:

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## Crear superusuario

```bash
python manage.py createsuperuser
```

## Cambiar clave del superusuario

```bash
python manage.py changepassword admin
```

---

## Levantar el servidor

```bash
python manage.py runserver 0.0.0.0:8000
```

Luego abre en el navegador:

- Front de kiosco: `http://localhost:8000/`
- Admin Django: `http://localhost:8000/admin/`
- Dashboard: `http://localhost:8000/panel/`
- Mesas de votación: `http://localhost:8000/panel/mesas/`
- Auditoría de padrón: `http://localhost:8000/panel/auditoria/`

---

## Comandos disponibles

Todos los comandos se ejecutan con el virtualenv activo y desde la raíz del
proyecto (`manage.py`). Usa `--help` sobre cualquier comando para ver todas
las opciones disponibles.

### 📥 Importar padrón electoral

Importa un CSV de estudiantes al proceso indicado. Valida DNI de 8 dígitos y
normaliza apellidos/nombres a mayúsculas.

```bash
python manage.py importar_padron --help
python manage.py importar_padron /ruta/al/archivo.csv --proceso 1
python manage.py importar_padron --file /ruta/completa/padron.csv --proceso 1
python manage.py importar_padron /ruta/al/archivo.csv --proceso 1 --crear-mesas
```

**Requisitos del CSV:**

- Columnas obligatorias: `item`, `dni`, `apellido_paterno`, `apellido_materno`,
  `nombres`, `nivel`, `grado`, `seccion`, `mesa`.
- El DNI debe ser numérico de 8 dígitos.
- La columna `mesa` debe coincidir con una mesa existente del proceso, o usar
  `--crear-mesas` para crearla automáticamente.
- `--proceso` es obligatorio y debe apuntar a un proceso existente.

Si el proceso no existe, el comando falla con:

```bash
CommandError: No existe el proceso electoral con id=...
```

Ver código en `apps/voters/management/commands/importar_padron.py`.

---

### 📦 Clonar padrón entre procesos

Copia todos los electores (y opcionalmente las mesas) de un proceso origen a
otro proceso destino. Útil para reutilizar el mismo colegio en elecciones
consecutivas.

```bash
python manage.py clonar_padron --origen 1 --destino 2
python manage.py clonar_padron --origen 1 --destino 2 --crear-mesas
python manage.py clonar_padron --origen 1 --destino 2 --crear-mesas --reset
```

**Opciones:**

| Flag | Descripción |
|---|---|
| `--origen <id>` | Proceso del cual copiar (obligatorio) |
| `--destino <id>` | Proceso al cual copiar (obligatorio) |
| `--crear-mesas` | Crea las mesas del origen en el destino si no existen |
| `--reset` | Limpia el padrón del destino antes de copiar |

Los estudiantes clonados arrancan **limpios** (`ha_votado=False`,
`inhabilitado=False`, `fecha_ausentismo=None`).

> ⚠️ Requiere que el campo `Estudiante.numero_documento` **no sea único
> globalmente**, sino único por proceso (`unique_together = ("proceso",
> "numero_documento")`). Si aún no aplicaste ese cambio, primero hazlo en
> `apps/voters/models.py` + migración.

---

### 🧹 Limpiar fotos y logos huérfanos

Recorre `media/listas/` y `media/logos/` y borra los archivos que ya no
están referenciados por ningún registro en la base de datos. Útil después de
borrados masivos o de reemplazos de imagen anteriores a la activación de signals.

```bash
python manage.py limpiar_fotos_huerfanas --dry-run
python manage.py limpiar_fotos_huerfanas
```

**Opciones:**

| Flag | Descripción |
|---|---|
| `--dry-run` | Solo reporta los archivos huérfanos, no los borra |

Se recomienda ejecutarlo primero con `--dry-run` para revisar la lista antes
de borrar.

---

### ♻️ Reiniciar votación del proceso

> Este comando se ejecuta **desde el panel de admin web**, no desde terminal.
> Aquí se documenta para referencia del flujo.

Ruta: `/admin/voters/procesoelectoral/`

1. Selecciona **un proceso activo** (checkbox).
2. En **Acciones**, elige **♻️ Reiniciar votación (borra todos los votos)**.
3. Clic en **Ir**.
4. En la pantalla de confirmación, opcionalmente escribe un motivo y confirma.

**Consecuencias:**

- Borra todos los `Voto` del proceso.
- Borra todos los `RegistroParticipacion` del proceso.
- Borra el `ActaCierreProceso` si existe (de un cierre previo).
- Resetea `ha_votado=False` y `fecha_ausentismo=None` en todos los estudiantes.
- Registra la acción en `AccionAdministrativa` con usuario, IP y motivo.

**Restricciones:**

- Solo funciona en procesos **activos y no cerrados**.
- Solo se permite seleccionar **un proceso** a la vez.
- La operación es **irreversible**.

---

### 📄 Generar acta en PDF

> Se ejecuta desde el panel de admin web.

Rutas:

- Desde el panel: `/panel/acta/<acta_id>/` → botón **📥 Descargar Acta en PDF**.
- Desde el admin: `/admin/voting/actacierreproceso/` → columna **PDF** → botón **📥 Descargar**.

Genera un PDF A4 con membrete institucional (logo + nombre), resumen global del
padrón, resultados por categoría con ganadores destacados y bloque de firmas.

**Requisito:** `xhtml2pdf` instalado (`pip install xhtml2pdf`).

---

### 🧪 Ejecutar tests

Corre toda la suite con `pytest`:

```bash
pytest -q
```

Para un archivo puntual:

```bash
pytest apps/voters/tests.py -q
pytest apps/voting/tests.py -q
pytest apps/core/tests.py -q
```

Para un test específico:

```bash
pytest apps/voters/tests.py::KioskValidationTests -q
pytest apps/voters/tests.py::KioskValidationTests::test_validar_dni_cinco_estados -v
```

---

### 🛠️ Comandos útiles de Django

```bash
# Ver todas las rutas registradas
python manage.py show_urls           # requiere django-extensions
python manage.py showmigrations

# Shell interactivo
python manage.py shell
python manage.py shell_plus          # requiere django-extensions

# Recolectar estáticos (para producción)
python manage.py collectstatic --noinput

# Limpiar sesiones expiradas
python manage.py clearsessions

# Ver el SQL de una migración
python manage.py sqlmigrate voters 0001

# Resetear la base de datos (¡CUIDADO! Borra todo)
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

---

### 🔐 Generar claves para el `.env`

```bash
# SECRET_KEY de Django
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# VOTE_KEY de Fernet (para cifrar boletas)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# HASH_SALT (cualquier cadena aleatoria)
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Pega los valores generados en el archivo `.env` de la raíz del proyecto.

---

## Estructura principal

```text
proy_cole_votaciones/
├── apps/
│   ├── auditoria/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── migrations/
│   │   ├── models.py
│   │   └── services.py
│   ├── candidates/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── migrations/
│   │   ├── models.py
│   │   └── signals.py
│   ├── core/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── crypto.py
│   │   ├── hashing.py
│   │   ├── models.py
│   │   └── tests.py
│   ├── voters/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── management/
│   │   │   └── commands/
│   │   │       ├── importar_padron.py
│   │   │       ├── clonar_padron.py
│   │   │       └── limpiar_fotos_huerfanas.py
│   │   ├── migrations/
│   │   ├── models.py
│   │   ├── selectors.py
│   │   ├── signals.py
│   │   └── tests.py
│   └── voting/
│       ├── admin.py
│       ├── apps.py
│       ├── context_processors.py
│       ├── migrations/
│       ├── models.py
│       ├── selectors.py
│       ├── services/
│       │   ├── cerrar_proceso.py
│       │   ├── emitir_voto.py
│       │   ├── iniciar_voto.py
│       │   ├── reiniciar_votacion.py
│       │   ├── reiniciar_voto.py
│       │   └── toggle_estudiante.py
│       ├── urls.py
│       └── views/
│           ├── auditoria.py
│           ├── cierre.py
│           ├── dashboard.py
│           ├── kiosk.py
│           └── mesas.py
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── media/                 # Archivos subidos (logos, fotos de listas)
├── requirements/
│   └── base.txt
├── static/
│   ├── css/
│   ├── js/
│   └── vendor/
├── templates/
│   ├── admin/
│   │   └── voters/
│   │       ├── estudiante/
│   │       │   └── mover_a_mesa.html
│   │       └── procesoelectoral/
│   │           └── reiniciar_votacion.html
│   ├── base.html
│   ├── 
│   │   ├── espera.html
│   │   ├── exito.html
│   │   └── wizard.html
│   └── voting/
│       ├── acta_detalle.html
│       ├── acta_pdf_template.html
│       ├── auditoria_padron.html
│       ├── cerrar_confirm.html
│       ├── dashboard.html
│       └── mesas_lista.html
├── db.sqlite3
├── manage.py
├── pytest.ini
├── README.md
└── requirements/
    └── base.txt
```

---

## Funcionalidades principales

- Validación de votos por DNI y flujo de kiosco con confirmación de identidad.
- Registro de participación y emisión de votos con integridad transaccional.
- Cifrado de boletas con Fernet y hash de integridad SHA-256.
- Dashboard de métricas en tiempo real con ECharts.
- Mesas de votación con vista de lista + detalle (participación por grado/sección).
- Auditoría de padrón con filtros jerárquicos (nivel → grado → sección) y export CSV.
- Acciones administrativas sobre el padrón: mover a mesa, inhabilitar, habilitar, reiniciar voto.
- Reinicio completo de votación por proceso (con confirmación).
- Cierre de proceso, registro de ausentes y generación de acta en PDF.
- Auditoría de todas las acciones administrativas (`AccionAdministrativa`).
- Subida de logos de proceso y fotos de listas con validación de tamaño/extension.

---

## Recomendación

Para desarrollar o validar cambios, siempre usa el entorno virtual del proyecto:

```bash
source venv/bin/activate
```

y luego ejecuta migraciones y tests desde la carpeta del proyecto.

---

## Usuario administrador

- URL: `http://localhost:8000/admin/`
- Usuario: `admin`
- Contraseña: `Proyecto4321`

> ⚠️ **Cambiar la contraseña en producción**: `python manage.py changepassword admin`


## **🚀 Carga inicial (datos demo)**

Para arrancar con una base de datos poblada sin tener que crear todo a mano,

el proyecto incluye un comando de **carga inicial** que genera:

- **1 superusuario** (`admin` / `admin` por defecto)
- **1 Proceso Electoral** activo (`Elecciones Demo 2026`)
- **2 Mesas de Votación** (`Mesa 1`, `Mesa 2`)
- **2 Tipos de Elección** (`Alcalde`, `Regidores`) con su color y orden
- **4 Listas de Candidatura** (2 por cada tipo)
- **4 Estudiantes** (2 por mesa, con DNI, grado, sección y mesa asignada)

El comando es **idempotente**: se puede ejecutar varias veces sin duplicar

registros. La contraseña del superusuario se fuerza en cada ejecución, así

que si te olvidas la clave, vuelve a correrlo.

### **Ejecución**

bash

```
# 1. Activar el virtualenv
source venv/bin/activate

# 2. Aplicar migraciones (si aún no lo hiciste)
python manage.py migrate

# 3. Cargar datos demo
python manage.py seed_demo

# 4. Levantar el servidor
python manage.py runserver 0.0.0.0:8000
```

### **Opciones del comando**

bash

```
python manage.py seed_demo --help
python manage.py seed_demo --reset
python manage.py seed_demo --admin-user=wilson --admin-pass=MiClave123
```

| **Flag** | **Descripción** |
| --- | --- |
| `--reset` | Borra el proceso demo (y todo en cascada) antes de recrearlo |
| `--admin-user <str>` | Usuario del superusuario (default: `admin`) |
| `--admin-pass <str>` | Contraseña del superusuario (default: `admin`) |
| `--admin-email <str>` | Email del superusuario (default: `admin@example.com`) |

> ⚠️ `--reset` **solo** borra el proceso `Elecciones Demo 2026`. Otros
> 
> 
> procesos que hayas creado manualmente **no** se tocan.
> 

### **Acceso después de la carga**

| **Recurso** | **URL** | **Credenciales** |
| --- | --- | --- |
| Admin Django | `http://localhost:8000/admin/` | `admin` / `admin` |
| Panel de control | `http://localhost:8000/panel/` | sesión del admin |
| Kiosco de votación | `http://localhost:8000/` | ver DNIs abajo |

### **DNIs listos para probar el kiosco**

| **DNI** | **Estudiante** | **Mesa** |
| --- | --- | --- |
| `42822315` | AGUILAR SANDOVAL, DEMO 01 | Mesa 1 |
| `42822316` | CHAPOÑAN DE LA CRUZ, DEMO 02 | Mesa 1 |
| `42822317` | PEREZ GOMEZ, DEMO 03 | Mesa 2 |
| `42822318` | ROJAS TORRES, DEMO 04 | Mesa 2 |

### **Flujo rápido de prueba**

1. Ve a `http://localhost:8000/admin/` → inicia sesión con `admin` / `admin`.
2. Entra a **Procesos Electorales** y verifica que `Elecciones Demo 2026` esté `activo` y no `cerrado`.
3. Abre `http://localhost:8000/` e ingresa uno de los DNIs de arriba.
4. Selecciona listas en cada paso del wizard, confirma con el DNI.
5. Verifica que el contador del panel se actualice en `http://localhost:8000/panel/`.

### **Notas**

- Los comandos `seed_demo`, `clonar_padron`, `importar_padron` y
    
    `limpiar_fotos_huerfanas` son **independientes**. Puedes usar `seed_demo`
    
    para tener una base mínima, y luego `importar_padron` para cargar el
    
    padrón real encima.
    
- Si ya tenías un proceso activo y ejecutas `seed_demo` sin `-reset`, se
    
    **sumará** como un proceso más. Para trabajar con uno solo, usa `--reset`
    
    antes o desactiva los procesos viejos desde el admin.
    
- Las listas creadas por el comando **no traen foto**. Puedes subirlas
    
    desde `/admin/candidates/listacandidatura/` después.
