from django.db import transaction

from apps.candidates.models import ListaCandidatura, TipoEleccion
from apps.core.crypto import cifrar_boleta, nueva_boleta
from apps.core.hashing import generar_hash_participacion
from apps.voters.models import Estudiante
from apps.voting.models import RegistroParticipacion, Voto


class ErrorVoto(Exception):
    pass


@transaction.atomic
def emitir_voto(estudiante_id, proceso, selecciones: dict[int, int]):
    estudiante = Estudiante.objects.select_for_update().get(id=estudiante_id, proceso=proceso)

    if not estudiante.es_activo or estudiante.inhabilitado:
        raise ErrorVoto("Elector no habilitado")
    if estudiante.ha_votado:
        raise ErrorVoto("El elector ya emitió su voto")

    tipos = list(TipoEleccion.objects.filter(proceso=proceso, es_activo=True).order_by("orden_aparicion"))
    if not tipos:
        raise ErrorVoto("No hay tipos de elección activos")

    if set(selecciones.keys()) != {tipo.id for tipo in tipos}:
        raise ErrorVoto("Selecciones incompletas")

    boleta = nueva_boleta()
    for tipo in tipos:
        lista_id = selecciones.get(tipo.id)
        if lista_id is None:
            raise ErrorVoto(f"Falta seleccionar una lista para {tipo.nombre}")
        if not ListaCandidatura.objects.filter(id=lista_id, tipo_eleccion=tipo, es_activo=True).exists():
            raise ErrorVoto(f"Lista inválida para {tipo.nombre}")

        Voto.objects.create(proceso=proceso, tipo_eleccion=tipo, lista_id=lista_id, boleta_id=boleta)

    hash_integridad, _ = generar_hash_participacion(estudiante, proceso)
    RegistroParticipacion.objects.create(
        proceso=proceso,
        estudiante=estudiante,
        hash_integridad=hash_integridad,
        boleta_cifrada=cifrar_boleta(boleta),
    )

    estudiante.ha_votado = True
    estudiante.save(update_fields=["ha_votado"])

    return boleta
