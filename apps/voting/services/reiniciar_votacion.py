"""Servicio: reiniciar la votación de un proceso electoral.

Elimina todos los votos emitidos, los registros de participación, el acta
de cierre (si existiera de un cierre anterior) y deja a los estudiantes en
estado 'Pendiente' (sin `ha_votado` ni `fecha_ausentismo`).

Solo se permite en procesos ACTIVOS y NO CERRADOS. Es irreversible.
"""

from django.db import transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.voters.models import Estudiante
from apps.voting.models import ActaCierreProceso, RegistroParticipacion, Voto


class ErrorReinicio(Exception):
    pass


@transaction.atomic
def reiniciar_votacion_proceso(proceso, usuario, motivo=""):
    """Reinicia la votación del proceso.

    Devuelve un dict con el resumen de la operación:
        {
            "votos_eliminados": int,
            "participaciones_eliminadas": int,
            "estudiantes_reseteados": int,
            "acta_eliminada": bool,
            "proceso": str,
        }
    """
    # -------- Validaciones de negocio --------
    if proceso.cerrado:
        raise ErrorReinicio(
            "El proceso ya está CERRADO. Solo se puede reiniciar la votación "
            "en procesos activos y no cerrados."
        )
    if not proceso.activo:
        raise ErrorReinicio(
            "El proceso no está ACTIVO. Solo se puede reiniciar la votación "
            "en procesos activos y no cerrados."
        )

    # -------- Borrar votos y participaciones --------
    votos_borrados = Voto.objects.filter(proceso=proceso).delete()[0]
    participaciones_borradas = (
        RegistroParticipacion.objects
        .filter(proceso=proceso)
        .delete()[0]
    )

    # -------- Borrar acta de cierre previa (si existe) --------
    acta_eliminada = False
    acta_qs = ActaCierreProceso.objects.filter(proceso=proceso)
    if acta_qs.exists():
        acta_qs.delete()
        acta_eliminada = True

    # -------- Resetear a los estudiantes --------
    estudiantes_afectados = (
        Estudiante.objects
        .filter(proceso=proceso)
        .update(
            ha_votado=False,
            fecha_ausentismo=None,
        )
    )

    # -------- Bitácora --------
    registrar(
        usuario,
        "reiniciar_votacion_proceso",
        proceso=proceso,
        detalle={
            "votos_eliminados": votos_borrados,
            "participaciones_eliminadas": participaciones_borradas,
            "estudiantes_reseteados": estudiantes_afectados,
            "acta_eliminada": acta_eliminada,
            "motivo": motivo,
            "timestamp": timezone.now().isoformat(),
        },
        entidad="ProcesoElectoral",
        entidad_id=proceso.id,
    )

    return {
        "votos_eliminados": votos_borrados,
        "participaciones_eliminadas": participaciones_borradas,
        "estudiantes_reseteados": estudiantes_afectados,
        "acta_eliminada": acta_eliminada,
        "proceso": proceso.nombre,
    }