import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.voters.models import Estudiante, GradoSeccion, MesaDeVotacion, ProcesoElectoral

DNI_RE = re.compile(r"^\d{8}$")
NUMERO_RE = re.compile(r"\d+")
REQUIRED_HEADERS = {
    "item",
    "dni",
    "apellido_paterno",
    "apellido_materno",
    "nombres",
    "nivel",
    "grado",
    "seccion",
}


def _normalize_text(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().split()).strip()


def _normalize_nivel(value):
    return _normalize_text(value).lower()


def _normalize_seccion(value):
    return _normalize_text(value).upper()


def _normalize_grado(value):
    return _normalize_text(value)


def _orden_grado(grado):
    """Deriva el orden numérico de un grado ('1ro' -> 1, '10mo' -> 10)."""
    match = NUMERO_RE.search(grado or "")
    return int(match.group()) if match else 0


class Command(BaseCommand):
    help = "Importa un padrón electoral desde un archivo CSV"

    def add_arguments(self, parser):
        parser.add_argument("file_path", nargs="?", help="Ruta al CSV del padrón")
        parser.add_argument("--file", dest="file_option", help="Ruta al CSV del padrón")
        parser.add_argument("--proceso", type=int, required=True, help="ID del proceso electoral")
        parser.add_argument("--crear-mesas", action="store_true", help="Crea mesas faltantes en el proceso")

    @transaction.atomic
    def handle(self, *args, **options):
        file_value = options.get("file_option") or options.get("file_path")
        if not file_value:
            raise CommandError("Debes indicar el CSV del padrón usando --file o como argumento posicional.")

        file_path = Path(file_value)
        if not file_path.exists():
            raise CommandError(f"No existe el archivo CSV: {file_path}")

        try:
            proceso = ProcesoElectoral.objects.get(pk=options["proceso"])
        except ProcesoElectoral.DoesNotExist:
            raise CommandError(f"No existe el proceso electoral con id={options['proceso']}")

        mesas = {m.numero_mesa: m for m in proceso.mesas.all()}
        # Cache de catálogo GradoSeccion: {(nivel, grado, seccion): GradoSeccion}
        grados_seccion = {
            (gs.nivel, gs.grado, gs.seccion): gs
            for gs in GradoSeccion.objects.all()
        }
        lote = []
        creados = 0
        errores = []
        batch_size = 500

        with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                raise CommandError("El archivo CSV está vacío o no tiene cabecera")

            normalized_headers = {(_normalize_text(h) or "").lower(): h for h in reader.fieldnames}
            missing = sorted(REQUIRED_HEADERS - set(normalized_headers.keys()))
            if missing:
                raise CommandError(f"Faltan columnas obligatorias en el CSV: {', '.join(missing)}")

            # La columna `mesa` es opcional: si no viene, el estudiante queda sin mesa.
            col_mesa = normalized_headers.get("mesa")

            for line_number, row in enumerate(reader, start=2):
                row = {key: value for key, value in row.items()}
                dni = _normalize_text(row.get(normalized_headers["dni"], ""))
                if not DNI_RE.match(dni):
                    errores.append((line_number, dni, "DNI inválido"))
                    continue

                # -------- Mesa (opcional) --------
                mesa = None
                mesa_raw = _normalize_text(row.get(col_mesa, "")) if col_mesa else ""
                if mesa_raw:
                    mesa = mesas.get(mesa_raw)
                    if mesa is None and options["crear_mesas"]:
                        mesa = MesaDeVotacion.objects.create(
                            proceso=proceso,
                            numero_mesa=mesa_raw,
                            descripcion=f"Aula {mesa_raw}",
                        )
                        mesas[mesa_raw] = mesa
                    if mesa is None:
                        errores.append((line_number, dni, f"Mesa no existe: {mesa_raw}"))
                        continue

                # -------- Grado y sección (catálogo global) --------
                nivel = _normalize_nivel(row.get(normalized_headers["nivel"], ""))
                grado = _normalize_grado(row.get(normalized_headers["grado"], ""))
                seccion = _normalize_seccion(row.get(normalized_headers["seccion"], ""))

                grado_seccion = None
                if grado and seccion:
                    key = (nivel, grado, seccion)
                    grado_seccion = grados_seccion.get(key)
                    if grado_seccion is None:
                        grado_seccion = GradoSeccion.objects.create(
                            nivel=nivel,
                            grado=grado,
                            seccion=seccion,
                            orden=_orden_grado(grado),
                        )
                        grados_seccion[key] = grado_seccion

                estudiante = Estudiante(
                    proceso=proceso,
                    mesa=mesa,
                    grado_seccion=grado_seccion,
                    numero_documento=dni,
                    apellido_paterno=_normalize_text(row.get(normalized_headers["apellido_paterno"], "")).upper(),
                    apellido_materno=_normalize_text(row.get(normalized_headers["apellido_materno"], "")).upper(),
                    nombres=_normalize_text(row.get(normalized_headers["nombres"], "")).upper(),
                )
                lote.append(estudiante)

                if len(lote) >= batch_size:
                    creados += len(Estudiante.objects.bulk_create(lote, ignore_conflicts=True))
                    lote.clear()

        if lote:
            creados += len(Estudiante.objects.bulk_create(lote, ignore_conflicts=True))

        self.stdout.write(self.style.SUCCESS(f"Creados: {creados}"))
        self.stdout.write(self.style.WARNING(f"Errores: {len(errores)}"))
        for line_number, dni, detalle in errores[:20]:
            self.stdout.write(f"  Línea {line_number} | DNI {dni} | {detalle}")
