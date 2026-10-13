from django.db import transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.voters.models import Estudiante


class ErrorAccion(Exception):
    pass


@transaction.atomic
def inhabilitar_estudiante(estudiante_id, usuario, motivo=""):
    estudiante = Estudiante.objects.select_for_update().get(id=estudiante_id)
    if estudiante.ha_votado or estudiante.fecha_ausentismo:
        raise ErrorAccion("No se puede inhabilitar a un estudiante con participación o ausentismo activo")

    estudiante.inhabilitado = True
    estudiante.es_activo = False
    estudiante.fecha_inhabilitacion = timezone.now()
    estudiante.save(update_fields=["inhabilitado", "es_activo", "fecha_inhabilitacion"])

    registrar(
        usuario,
        "inhabilitar",
        estudiante=estudiante,
        detalle={"motivo": motivo},
        entidad="Estudiante",
        entidad_id=estudiante.id,
    )
    return estudiante


@transaction.atomic
def habilitar_estudiante(estudiante_id, usuario):
    estudiante = Estudiante.objects.select_for_update().get(id=estudiante_id)
    if not estudiante.inhabilitado:
        raise ErrorAccion("El estudiante no está inhabilitado")

    estudiante.inhabilitado = False
    estudiante.es_activo = True
    estudiante.fecha_inhabilitacion = None
    estudiante.save(update_fields=["inhabilitado", "es_activo", "fecha_inhabilitacion"])

    registrar(
        usuario,
        "habilitar",
        estudiante=estudiante,
        detalle={},
        entidad="Estudiante",
        entidad_id=estudiante.id,
    )
    return estudiante
