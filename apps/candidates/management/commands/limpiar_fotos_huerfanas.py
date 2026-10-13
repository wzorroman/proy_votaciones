"""Borra archivos en MEDIA_ROOT que no estén referenciados en la BD.

Útil para limpiar fotos/logos huérfanos acumulados de reemplazos o
borrados masivos antes de tener signals.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.candidates.models import ListaCandidatura
from apps.voters.models import ProcesoElectoral


class Command(BaseCommand):
    help = "Elimina fotos y logos huérfanos en MEDIA_ROOT."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo reporta, no borra.",
        )

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        referenciados = set()

        # Rutas referenciadas en la BD
        for ruta in ListaCandidatura.objects.exclude(foto="").values_list("foto", flat=True):
            referenciados.add(os.path.normpath(os.path.join(settings.MEDIA_ROOT, ruta)))

        for ruta in ProcesoElectoral.objects.exclude(logo="").values_list("logo", flat=True):
            referenciados.add(os.path.normpath(os.path.join(settings.MEDIA_ROOT, ruta)))

        # Recorre media/listas y media/logos
        huerfanos = []
        for sub in ("listas", "logos"):
            base = os.path.join(settings.MEDIA_ROOT, sub)
            if not os.path.isdir(base):
                continue
            for root, _dirs, files in os.walk(base):
                for f in files:
                    full = os.path.normpath(os.path.join(root, f))
                    if full not in referenciados:
                        huerfanos.append(full)

        if not huerfanos:
            self.stdout.write(self.style.SUCCESS("No hay archivos huérfanos."))
            return

        for path in huerfanos:
            self.stdout.write(f"{'[DRY]' if dry else '[DEL]'} {path}")
            if not dry:
                try:
                    os.remove(path)
                except OSError as exc:
                    self.stderr.write(f"No se pudo borrar {path}: {exc}")

        self.stdout.write(self.style.WARNING(
            f"Total: {len(huerfanos)} archivo(s) {'detectados' if dry else 'eliminados'}."
        ))
