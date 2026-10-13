"""Servicio: quitar la asignación de mesa a uno o varios estudiantes.

Pensado para invocarse desde el Django Admin (acción masiva sobre el
changelist de `Estudiante`) y desde cualquier vista/management command
que necesite liberar mesas de un grupo de votantes.

Reglas de negocio:
    * Solo se limpia la mesa de estudiantes que NO han emitido su voto.
    * Los estudiantes que ya estaban sin mesa se cuentan aparte (no se
      vuelve a tocar su registro, pero se reportan).
    * La acción se registra en la auditoría una vez por proceso afectado.
"""

from collections import defaultdict

from django.db import transaction

from apps.auditoria.services import registrar
from apps.voters.models import Estudiante, ProcesoElectoral


class ErrorLimpiarMesa(Exception):
    """Errores recuperables al intentar limpiar mesas."""


@transaction.atomic
def limpiar_mesa_estudiantes(estudiantes, usuario, motivo="", ip=None):
    """Quita la asignación de mesa a cada estudiante del queryset/iterable.

    Parámetros:
        estudiantes: queryset o iterable de `Estudiante`.
        usuario:     usuario que ejecuta la acción (para auditoría).
        motivo:      texto libre que se almacena en la auditoría.
        ip:          IP de origen (opcional, para auditoría).

    Retorna un resumen:
        {
            "actualizados":       int,  # mesas limpiadas
            "omitidos_por_voto":  int,  # ya habian votado, no se tocan
            "ya_sin_mesa":        int,  # ya estaban sin mesa
            "por_proceso":        dict, # {proceso_id: [ids]}
        }
    """
    qs = estudiantes if hasattr(estudiantes, "filter") else Estudiante.objects.filter(
        id__in=[e.id for e in estudiantes]
    )

    if not qs.exists():
        raise ErrorLimpiarMesa("No se proporcionaron estudiantes para limpiar.")

    omitidos_por_voto = qs.filter(ha_votado=True).count()
    ya_sin_mesa = qs.filter(mesa__isnull=True).count()
    candidatos = qs.exclude(ha_votado=True).filter(mesa__isnull=False)

    if candidatos.count() == 0:
        return {
            "actualizados": 0,
            "omitidos_por_voto": omitidos_por_voto,
            "ya_sin_mesa": ya_sin_mesa,
            "por_proceso": {},
        }

    por_proceso = defaultdict(list)
    for pid, eid in candidatos.values_list("proceso_id", "id"):
        por_proceso[pid].append(eid)

    ids_afectados = list(candidatos.values_list("id", flat=True))
    actualizados = candidatos.update(mesa=None)

    for pid, eids in por_proceso.items():
        proceso = ProcesoElectoral.objects.filter(pk=pid).first()
        registrar(
            usuario,
            "limpiar_mesa_estudiantes",
            detalle={
                "total": len(eids),
                "estudiantes_ids": eids,
                "motivo": motivo or "Limpieza de mesa",
                "omitidos_por_voto": omitidos_por_voto,
            },
            proceso=proceso,
            ip=ip,
            entidad="Estudiante",
            entidad_id=pid,
        )

    return {
        "actualizados": actualizados,
        "omitidos_por_voto": omitidos_por_voto,
        "ya_sin_mesa": ya_sin_mesa,
        "por_proceso": dict(por_proceso),
    }