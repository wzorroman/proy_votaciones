"""Servicio: iniciar oficialmente la votación de un proceso electoral.

Antes de habilitar el kiosco se comprueba que TODO el padrón tenga mesa
asignada (y grado/sección). Si falta alguno, se rechaza el inicio para
evitar abrir la jornada con datos incompletos.
"""

from django.db import transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.voting import selectors


class ErrorInicio(Exception):
    pass


def autopausar_si_sin_votantes(proceso):
    """Pausa automáticamente el proceso si NO tiene votantes asignados.

    Devuelve True si se aplicó (o ya estaba aplicada) la pausa automática.
    De esta forma el kiosco queda bloqueado hasta que se asigne al menos
    1 votante a una mesa.
    """
    if proceso is None:
        return False
    if not selectors.proceso_sin_votantes_asignados(proceso):
        return False
    if proceso.votacion_iniciada and not proceso.votacion_pausada:
        proceso.votacion_pausada = True
        proceso.save(update_fields=["votacion_pausada"])
    return True


@transaction.atomic
def iniciar_votacion_proceso(proceso, usuario):
    """Marca el proceso como «votación iniciada» tras validar el padrón.

    Devuelve un dict resumen:
        {"sin_mesa": int, "sin_grado_seccion": int, "fecha_inicio": datetime}

    Lanza ErrorInicio si el proceso está cerrado o si el padrón no está
    completamente categorizado/asignado.
    """
    if proceso.cerrado:
        raise ErrorInicio("El proceso ya está cerrado; no se puede iniciar.")
    if proceso.votacion_iniciada:
        raise ErrorInicio("La votación ya fue iniciada.")

    # Debe existir al menos 1 votante con mesa asignada para poder votar.
    asignados = proceso.estudiantes.filter(mesa__isnull=False).count()
    if asignados == 0:
        raise ErrorInicio(
            "No se puede iniciar: aún no se han asignado estudiantes a las mesas."
        )

    sin_mesa = proceso.estudiantes.filter(mesa__isnull=True).count()
    if sin_mesa:
        raise ErrorInicio(
            f"No se puede iniciar: {sin_mesa} estudiante(s) sin mesa asignada."
        )

    sin_grado_seccion = proceso.estudiantes.filter(grado_seccion__isnull=True).count()
    if sin_grado_seccion:
        raise ErrorInicio(
            f"No se puede iniciar: {sin_grado_seccion} estudiante(s) sin grado/sección."
        )

    ahora = timezone.now()
    proceso.votacion_iniciada = True
    proceso.fecha_inicio = ahora
    proceso.save(update_fields=["votacion_iniciada", "fecha_inicio"])

    registrar(
        usuario,
        "iniciar_votacion",
        proceso=proceso,
        detalle={"fecha_inicio": ahora.isoformat(), "total_electores": proceso.estudiantes.count()},
        entidad="ProcesoElectoral",
        entidad_id=proceso.id,
    )

    return {"sin_mesa": sin_mesa, "sin_grado_seccion": sin_grado_seccion, "fecha_inicio": ahora}


@transaction.atomic
def pausar_votacion_proceso(proceso, usuario, motivo=""):
    """Pausa temporalmente la jornada: el kiosco queda bloqueado hasta reanudar."""
    if proceso.cerrado:
        raise ErrorInicio("El proceso ya está cerrado; no se puede pausar.")
    if not proceso.votacion_iniciada:
        raise ErrorInicio("La votación aún no ha comenzado.")
    if proceso.votacion_pausada:
        raise ErrorInicio("La votación ya está en pausa.")

    proceso.votacion_pausada = True
    proceso.save(update_fields=["votacion_pausada"])

    registrar(
        usuario,
        "pausar_votacion",
        proceso=proceso,
        detalle={"motivo": motivo},
        entidad="ProcesoElectoral",
        entidad_id=proceso.id,
    )
    return {"pausada": True}


@transaction.atomic
def reanudar_votacion_proceso(proceso, usuario):
    """Reanuda la jornada previamente pausada."""
    if proceso.cerrado:
        raise ErrorInicio("El proceso ya está cerrado; no se puede reanudar.")
    if not proceso.votacion_pausada:
        raise ErrorInicio("La votación no está en pausa.")
    asignados = proceso.estudiantes.filter(mesa__isnull=False).count()
    if asignados == 0:
        raise ErrorInicio(
            "No se puede reanudar: aún no se han asignado estudiantes a las mesas."
        )

    proceso.votacion_pausada = False
    proceso.save(update_fields=["votacion_pausada"])

    registrar(
        usuario,
        "reanudar_votacion",
        proceso=proceso,
        detalle={},
        entidad="ProcesoElectoral",
        entidad_id=proceso.id,
    )
    return {"pausada": False}
