"""Vista de Mesas de Votación (panel admin).

Muestra un listado de mesas con métricas en vivo a la izquierda y un
panel de detalle de la mesa seleccionada a la derecha.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, F, Q
from django.shortcuts import render

from apps.voters.models import ProcesoElectoral
from apps.voting import selectors


@staff_member_required
def mesas_lista_view(request):
    proceso = ProcesoElectoral.objects.filter(activo=True, cerrado=False).first()
    if not proceso:
        return render(request, "voting/admin_sin_proceso.html")

    # ---------- Lista de mesas con métricas ----------
    mesas_data = selectors.participacion_por_mesa(proceso)
    for m in mesas_data:
        m["porcentaje"] = (
            round((m["emitidos"] / m["habiles"] * 100), 1)
            if m["habiles"] else 0.0
        )

    # ---------- Mesa seleccionada (por ?mesa=ID) ----------
    mesa_id = request.GET.get("mesa")
    mesa_sel = None
    if mesa_id and str(mesa_id).isdigit():
        mesa_sel = proceso.mesas.filter(id=mesa_id).first()

    # Fallback: primera mesa del listado
    if not mesa_sel and mesas_data:
        primera_num = mesas_data[0]["numero_mesa"]
        mesa_sel = proceso.mesas.filter(numero_mesa=primera_num).first()

    # ---------- Detalle de la mesa seleccionada ----------
    detalle = []
    mesa_habiles = mesa_emitidos = mesa_faltantes = 0
    mesa_pct = 0.0

    if mesa_sel:
        habiles_qs = mesa_sel.estudiantes.filter(
            es_activo=True, inhabilitado=False
        )
        mesa_habiles = habiles_qs.count()
        mesa_emitidos = habiles_qs.filter(ha_votado=True).count()
        mesa_faltantes = mesa_habiles - mesa_emitidos
        mesa_pct = (
            round((mesa_emitidos / mesa_habiles * 100), 1)
            if mesa_habiles else 0.0
        )

        detalle = list(
            mesa_sel.estudiantes
            .values(
                grado=F("grado_seccion__grado"),
                seccion=F("grado_seccion__seccion"),
            )
            .annotate(
                total=Count("id"),
                emitidos=Count("id", filter=Q(ha_votado=True)),
            )
            .order_by("grado", "seccion")
        )
        for d in detalle:
            d["porcentaje"] = (
                round((d["emitidos"] / d["total"] * 100), 1)
                if d["total"] else 0.0
            )

    context = {
        "proceso": proceso,
        "mesas": mesas_data,
        "total_mesas": len(mesas_data),
        "total_habiles": sum(m["habiles"] for m in mesas_data),
        "total_emitidos": sum(m["emitidos"] for m in mesas_data),
        "mesa_sel": mesa_sel,
        "mesa_habiles": mesa_habiles,
        "mesa_emitidos": mesa_emitidos,
        "mesa_faltantes": mesa_faltantes,
        "mesa_pct": mesa_pct,
        "detalle": detalle,
    }
    return render(request, "voting/mesas_lista.html", context)
