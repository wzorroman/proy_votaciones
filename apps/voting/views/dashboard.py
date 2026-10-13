from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import redirect, render

from apps.voters.models import ProcesoElectoral
from apps.voting import selectors
from apps.voting.services.iniciar_votacion import (
    ErrorInicio,
    autopausar_si_sin_votantes,
    iniciar_votacion_proceso,
    pausar_votacion_proceso,
    reanudar_votacion_proceso,
)


def _proceso_activo():
    return ProcesoElectoral.objects.filter(activo=True, cerrado=False).first()


def _autopaused_sin_votantes(proceso):
    """Atajo: delega en el servicio `autopausar_si_sin_votantes`."""
    return autopausar_si_sin_votantes(proceso)


@staff_member_required
def dashboard_live_json(request):
    proceso = _proceso_activo()
    if not proceso:
        return JsonResponse({"activo": False})

    sin_votantes = _autopaused_sin_votantes(proceso)
    desglose = selectors.participacion_por_grado_seccion(proceso)

    return JsonResponse({
        "activo": True,
        "votacion_iniciada": proceso.votacion_iniciada,
        "votacion_pausada": proceso.votacion_pausada,
        "sin_votantes_asignados": sin_votantes,
        "general": selectors.metricas_generales(proceso),
        "mesas": selectors.participacion_por_mesa(proceso),
        "grados": desglose["grados"],
        "secciones": desglose["secciones"],
        "asignacion_mesas": selectors.resumen_asignacion_mesas(proceso),
    })


@staff_member_required
def dashboard_view(request):
    proceso = _proceso_activo()

    general = {
        "habiles": 0, "emitidos": 0, "faltantes": 0, "porcentaje": 0.0,
    }
    mesas = []
    grados = []
    secciones = []
    detalle_grado_seccion = []
    detalle_total = 0
    asignacion_mesas = {"total": 0, "asignados": 0, "sin_mesa": 0, "porcentaje": 0.0}
    sin_votantes_asignados = False

    if proceso:
        sin_votantes_asignados = _autopaused_sin_votantes(proceso)
        general = selectors.metricas_generales(proceso)
        mesas = selectors.participacion_por_mesa(proceso)
        desglose = selectors.participacion_por_grado_seccion(proceso)
        grados = desglose["grados"]
        secciones = desglose["secciones"]
        detalle_grado_seccion = selectors.desglose_grado_seccion_por_mesa(proceso)
        detalle_total = sum(m["habiles"] for m in detalle_grado_seccion)
        asignacion_mesas = selectors.resumen_asignacion_mesas(proceso)

    data = {
        "activo": bool(proceso),
        "proceso": proceso,
        "general": general,
        "mesas": mesas,
        "grados": grados,
        "secciones": secciones,
        "detalle_grado_seccion": detalle_grado_seccion,
        "detalle_total": detalle_total,
        "asignacion_mesas": asignacion_mesas,
        "sin_votantes_asignados": sin_votantes_asignados,
    }
    return render(request, "voting/dashboard.html", data)


@staff_member_required
def iniciar_votacion_view(request):
    if request.method != "POST":
        return redirect("dashboard")

    proceso = _proceso_activo()
    if not proceso:
        messages.error(request, "No hay un proceso electoral activo.")
        return redirect("dashboard")

    try:
        iniciar_votacion_proceso(proceso, request.user)
        messages.success(request, "Votación iniciada. El kiosco ya está habilitado.")
    except ErrorInicio as exc:
        messages.error(request, f"No se pudo iniciar la votación: {exc}")

    return redirect("dashboard")


@staff_member_required
def pausar_votacion_view(request):
    if request.method != "POST":
        return redirect("dashboard")

    proceso = _proceso_activo()
    if not proceso:
        messages.error(request, "No hay un proceso electoral activo.")
        return redirect("dashboard")

    try:
        pausar_votacion_proceso(proceso, request.user, motivo=(request.POST.get("motivo") or "").strip())
        messages.warning(request, "Votación pausada. El kiosco quedó bloqueado temporalmente.")
    except ErrorInicio as exc:
        messages.error(request, f"No se pudo pausar la votación: {exc}")

    return redirect("dashboard")


@staff_member_required
def reanudar_votacion_view(request):
    if request.method != "POST":
        return redirect("dashboard")

    proceso = _proceso_activo()
    if not proceso:
        messages.error(request, "No hay un proceso electoral activo.")
        return redirect("dashboard")

    try:
        reanudar_votacion_proceso(proceso, request.user)
        messages.success(request, "Votación reanudada. El kiosco está habilitado nuevamente.")
    except ErrorInicio as exc:
        messages.error(request, f"No se pudo reanudar la votación: {exc}")

    return redirect("dashboard")
