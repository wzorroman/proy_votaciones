#!/usr/bin/env sh
set -e

echo "[entrypoint] Esperando a la base de datos..."
python <<'PY'
import os, time, socket
import environ

if os.path.exists("/app/.env"):
    environ.Env.read_env("/app/.env")

env = environ.Env()
db_config = env.db_url("DATABASE_URL", default="sqlite:///db.sqlite3")
engine = db_config["ENGINE"]

if engine.endswith("sqlite3"):
    db_path = db_config["NAME"]
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    print(f"[entrypoint] SQLite listo en {db_path}.")
else:
    host, port = db_config["HOST"], db_config["PORT"]
    for _ in range(30):
        try:
            with socket.create_connection((host, int(port)), timeout=2):
                print(f"[entrypoint] DB {host}:{port} alcanzable.")
                break
        except OSError:
            time.sleep(1)
    else:
        raise SystemExit(f"[entrypoint] No se pudo conectar a {host}:{port}")
PY

echo "[entrypoint] Aplicando migraciones..."
python manage.py migrate --noinput

echo "[entrypoint] Recolectando archivos estaticos..."
python manage.py collectstatic --noinput

# Carga opcional de datos demo. Se controla con LOAD_DEMO_DATA=true en .env.
# Usar LOAD_DEMO_RESET=true ademas para borrar el proceso demo antes.
if [ "${LOAD_DEMO_DATA:-false}" = "true" ]; then
    echo "[entrypoint] Cargando datos demo (seed_demo)..."
    SEED_ARGS="--admin-user=${LOAD_DEMO_ADMIN_USER:-admin} \
               --admin-pass=${LOAD_DEMO_ADMIN_PASS:-admin} \
               --admin-email=${LOAD_DEMO_ADMIN_EMAIL:-admin@example.com}"
    if [ "${LOAD_DEMO_RESET:-false}" = "true" ]; then
        SEED_ARGS="$SEED_ARGS --reset"
    fi
    python manage.py seed_demo $SEED_ARGS || \
        echo "[entrypoint] Aviso: seed_demo finalizo con errores."
fi

echo "[entrypoint] Iniciando servidor..."
exec "$@"