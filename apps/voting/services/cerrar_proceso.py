from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.candidates.models import TipoEleccion
from apps.voters.selectors import electores_habiles
from apps.voting.models import ActaCierreProceso, RegistroParticipacion, Voto


@transaction.atomic
def cerrar_proceso(proceso, usuario):
    if not proceso.activo or proceso.cerrado:
        raise ValueError("El proceso no puede cerrarse")

    ahora = timezone.now()
    proceso.activo = False
    proceso.cerrado = True
    proceso.fecha_cierre = ahora
    proceso.save(update_fields=["activo", "cerrado", "fecha_cierre"])

    habiles_qs = electores_habiles(proceso)
    habiles_qs.filter(ha_votado=False, fecha_ausentismo__isnull=True).update(fecha_ausentismo=ahora)

    habiles = habiles_qs.count()
    emitidos = RegistroParticipacion.objects.filter(proceso=proceso).count()
    ausentes = habiles_qs.filter(fecha_ausentismo__isnull=False).count()

    tipos = list(TipoEleccion.objects.filter(proceso=proceso, es_activo=True).order_by("orden_aparicion"))
    total_votos = Voto.objects.filter(proceso=proceso).count()
    if tipos and emitidos * len(tipos) != total_votos:
        raise ValueError("Los votos no concilian con las participaciones; no se cierra")

    resultados = {}
    for tipo in tipos:
        filas = list(
            Voto.objects.filter(proceso=proceso, tipo_eleccion=tipo)
            .values("lista_id", "lista__nombre")
            .annotate(votos=Count("id"))
            .order_by("-votos", "lista_id")
        )
        total = sum(item["votos"] for item in filas) or 1
        ganador_id = filas[0]["lista_id"] if filas else None
        resultados[tipo.nombre.lower().replace(" ", "_")] = [
            {
                "lista_id": item["lista_id"],
                "lista": item["lista__nombre"],
                "votos": item["votos"],
                "porcentaje": round(item["votos"] / total * 100, 1) if total else 0.0,
                "ganador": item["lista_id"] == ganador_id,
            }
            for item in filas
        ]

    acta = ActaCierreProceso.objects.create(
        proceso=proceso,
        total_electores_habiles=habiles,
        total_votos_emitidos=emitidos,
        total_ausentes=ausentes,
        resultados_consolidados=resultados,
        fecha_cierre_oficial=ahora,
    )

    RegistroParticipacion.objects.filter(proceso=proceso).update(boleta_cifrada=None)
    Voto.objects.filter(proceso=proceso).update(boleta_id=None)

    registrar(
        usuario,
        "cerrar_proceso",
        proceso=proceso,
        detalle={"habiles": habiles, "emitidos": emitidos, "ausentes": ausentes, "acta_id": acta.id},
        entidad="ProcesoElectoral",
        entidad_id=proceso.id,
    )

    return acta
