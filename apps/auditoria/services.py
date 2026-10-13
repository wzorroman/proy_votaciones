from django.utils import timezone

from apps.auditoria.models import AccionAdministrativa


def registrar(usuario, accion, *, proceso=None, estudiante=None, detalle=None, ip=None, entidad=None, entidad_id=None):
    detalle = detalle or {}
    entidad = entidad or (estudiante.__class__.__name__ if estudiante else "")
    entidad_id = entidad_id if entidad_id is not None else (estudiante.id if estudiante else None)

    return AccionAdministrativa.objects.create(
        usuario=usuario,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        detalle=detalle,
        ip=ip,
    )
