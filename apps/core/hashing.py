import hashlib

from django.conf import settings
from django.utils import timezone


def generar_hash_participacion(estudiante, proceso):
    """Genera una firma SHA-256 del proceso y del DNI del estudiante.

    La firma incluye el timestamp actual para asegurar que dos participaciones
    del mismo estudiante en el mismo proceso no produzcan el mismo hash.
    """
    ts = timezone.now().isoformat()
    payload = f"{proceso.id}|{estudiante.numero_documento}|{ts}|{settings.HASH_SALT}"
    firma = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return firma, ts
