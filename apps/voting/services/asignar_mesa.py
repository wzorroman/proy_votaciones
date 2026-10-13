"""Servicio: asignar todos los estudiantes de un grado/sección a una mesa.

El `GradoSeccion` es un catálogo global, por lo que el proceso se deriva de la
mesa destino (`mesa.proceso`). Solo se reasignan alumnos de ese proceso.

Regla de negocio: si algún alumno del grado/sección seleccionado ya emitió su
voto, se rechaza la operación y se pide reiniciar la votación del proceso.
"""

from django.db import transaction

from apps.auditoria.services import registrar
from apps.voters.models import Estudiante


class ErrorAsignacion(Exception):
    pass


@transaction.atomic
def asignar_mesa_a_grado_seccion(grado_secciones, mesa, usuario, motivo="", ip=None):
    """Mueve a `mesa` los alumnos del proceso de `mesa` que pertenecen a los
    grado/secciones indicados y que aún no han votado.

    Lanza `ErrorAsignacion` si algún alumno de ese proceso y grado/sección ya
    emitió su voto (debe reiniciarse la votación primero).
    """
    proceso = mesa.proceso
    ids = [gs.id for gs in grado_secciones]
    if not ids:
        raise ErrorAsignacion("No se seleccionó ningún grado/sección.")

    qs = Estudiante.objects.filter(proceso=proceso, grado_seccion_id__in=ids)

    votaron = qs.filter(ha_votado=True).count()
    if votaron:
        raise ErrorAsignacion(
            f"{votaron} estudiante(s) del grado/sección seleccionado ya emitieron su voto. "
            f"Reinicie la votación del proceso «{proceso.nombre}» antes de moverlos a otra mesa."
        )

    actualizados = qs.update(mesa=mesa)

    registrar(
        usuario,
        "asignar_mesa_a_grado_seccion",
        detalle={
            "mesa_destino_id": mesa.id,
            "mesa_destino": str(mesa),
            "proceso_id": proceso.id,
            "proceso": proceso.nombre,
            "grado_seccion_ids": ids,
            "grado_secciones": [str(gs) for gs in grado_secciones],
            "total": actualizados,
            "motivo": motivo,
        },
        entidad="MesaDeVotacion",
        entidad_id=mesa.id,
        ip=ip,
    )

    return {
        "total": actualizados,
        "mesa": str(mesa),
        "proceso": proceso.nombre,
        "grado_secciones": [str(gs) for gs in grado_secciones],
    }
