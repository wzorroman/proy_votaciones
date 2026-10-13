from django.db import transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.core.crypto import descifrar_boleta
from apps.voters.models import Estudiante
from apps.voting.models import RegistroParticipacion, Voto


class ErrorAccion(Exception):
    pass


@transaction.atomic
def reiniciar_voto(estudiante_id, usuario, motivo=""):
    estudiante = (
        Estudiante.objects.select_for_update()
        .select_related("proceso")
        .get(id=estudiante_id)
    )
    proceso = estudiante.proceso

    if proceso.cerrado:
        raise ErrorAccion("Proceso cerrado: el vínculo voto-elector ya fue destruido")
    if not estudiante.ha_votado:
        raise ErrorAccion("No hay voto que reiniciar")

    participacion = (
        RegistroParticipacion.objects.select_for_update()
        .filter(proceso=proceso, estudiante=estudiante)
        .first()
    )
    if not participacion or not participacion.boleta_cifrada:
        raise ErrorAccion("La participación no tiene boleta vinculada")

    boleta = descifrar_boleta(participacion.boleta_cifrada)
    borrados, _ = Voto.objects.filter(proceso=proceso, boleta_id=boleta).delete()
    esperados = proceso.tipos_eleccion.filter(es_activo=True).count()
    if borrados != esperados:
        raise ErrorAccion(f"Integridad: se esperaban {esperados} votos y se hallaron {borrados}")

    participacion.delete()
    estudiante.ha_votado = False
    estudiante.fecha_ausentismo = None
    estudiante.save(update_fields=["ha_votado", "fecha_ausentismo"])

    registrar(
        usuario,
        "reiniciar_voto",
        estudiante=estudiante,
        detalle={"votos_eliminados": borrados, "motivo": motivo},
        entidad="Estudiante",
        entidad_id=estudiante.id,
    )
    return borrados
