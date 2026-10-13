import csv

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.voters.models import Estudiante, ProcesoElectoral
from apps.voting import selectors
from apps.voting.models import RegistroParticipacion
from apps.voting.services.reiniciar_voto import ErrorAccion as ErrorReinicio
from apps.voting.services.reiniciar_voto import reiniciar_voto
from apps.voting.services.toggle_estudiante import (
    ErrorAccion as ErrorToggle,
)
from apps.voting.services.toggle_estudiante import (
    habilitar_estudiante,
    inhabilitar_estudiante,
)

PER_PAGE = 25


def _proceso_activo():
    return ProcesoElectoral.objects.filter(activo=True, cerrado=False).first()


def _qs_filtrado(request, proceso):
    q        = (request.GET.get("q") or "").strip()
    mesa_id  = request.GET.get("mesa") or None
    nivel    = request.GET.get("nivel") or None
    grado    = request.GET.get("grado") or None
    seccion  = request.GET.get("seccion") or None
    estado   = request.GET.get("estado") or None

    qs = selectors.filtros_padron(
        proceso,
        q=q, mesa_id=mesa_id,
        nivel=nivel, grado=grado, seccion=seccion,
        estado=estado,
    )
    return qs, {
        "q": q, "mesa": mesa_id or "",
        "nivel": nivel or "", "grado": grado or "", "seccion": seccion or "",
        "estado": estado or "",
    }


def _querystring_sin_page(request):
    """Devuelve la querystring actual sin el parámetro `page`.

    Se usa en la paginación y en el botón Export CSV para preservar filtros.
    """
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


@staff_member_required
def auditoria_padron_view(request):
    proceso = _proceso_activo()
    if not proceso:
        return render(request, "voting/admin_sin_proceso.html")

    qs, filtros = _qs_filtrado(request, proceso)

    # Exportación CSV: mismo queryset, sin paginar
    if request.GET.get("export") == "csv":
        return _exportar_csv(proceso, qs)

    # Paginación
    page_number = request.GET.get("page") or 1
    page = Paginator(qs, PER_PAGE).get_page(page_number)

    # Enriquecer la página con su RegistroParticipacion (para el modal "Ver")
    ids_pagina = [e.id for e in page.object_list]
    participaciones = {
        p.estudiante_id: p
        for p in RegistroParticipacion.objects.filter(
            proceso=proceso, estudiante_id__in=ids_pagina
        )
    }
    for est in page.object_list:
        est.participacion = participaciones.get(est.id)

    context = {
        "proceso": proceso,
        "page": page,
        "mesas": selectors.lista_mesas(proceso),
        "niveles": selectors.lista_niveles(proceso),
        # Grado depende de Nivel (si está seleccionado)
        "grados": selectors.lista_grados(proceso, nivel=filtros["nivel"] or None),
        # Sección depende de Nivel + Grado (si están seleccionados)
        "secciones": selectors.lista_secciones(
            proceso,
            nivel=filtros["nivel"] or None,
            grado=filtros["grado"] or None,
        ),
        "filtros": filtros,
        "total_filtrado": qs.count(),
        "querystring_sin_page": _querystring_sin_page(request),
    }
    return render(request, "voting/auditoria_padron.html", context)

def _exportar_csv(proceso, qs):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="padron_{proceso.id}.csv"'
    )
    response.write("\ufeff")  # BOM para Excel

    writer = csv.writer(response)
    writer.writerow(
        ["ITEM", "DNI", "APELLIDOS Y NOMBRES", "NIVEL", "GRADO", "SECCION", "MESA", "ESTADO"]
    )
    for i, est in enumerate(qs.iterator(), start=1):
        if est.ha_votado and not est.fecha_ausentismo and not est.inhabilitado:
            estado = "VOTO EMITIDO"
        elif est.inhabilitado:
            estado = "INHABILITADO"
        elif est.fecha_ausentismo:
            estado = "AUSENTE"
        else:
            estado = "PENDIENTE"
        writer.writerow(
            [
                i,
                est.numero_documento,
                f"{est.apellido_paterno} {est.apellido_materno}, {est.nombres}".strip(", "),
                est.grado_seccion.nivel if est.grado_seccion else "",
                est.grado_seccion.grado if est.grado_seccion else "",
                est.grado_seccion.seccion if est.grado_seccion else "",
                est.mesa.numero_mesa if est.mesa else "",
                estado,
            ]
        )
    return response


def _url_volver(request):
    """Reconstruye la URL de retorno conservando los filtros."""
    qs = request.POST.get("next") or request.GET.get("next")
    if qs:
        return f"{request.path}?{qs}"
    return request.path


@staff_member_required
def reiniciar_voto_estudiante(request, estudiante_id):
    if request.method != "POST":
        return redirect("auditoria_padron")

    motivo = (request.POST.get("motivo") or "").strip()
    try:
        borrados = reiniciar_voto(estudiante_id, request.user, motivo=motivo)
        messages.success(
            request,
            f"Voto reiniciado. Se eliminaron {borrados} registros de la urna anónima.",
        )
    except ErrorReinicio as exc:
        messages.error(request, f"No se pudo reiniciar: {exc}")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Error inesperado: {exc}")

    return redirect(_url_volver(request))


@staff_member_required
def cambiar_estado_habilitacion_estudiante(request, estudiante_id):
    if request.method != "POST":
        return redirect("auditoria_padron")

    accion = request.POST.get("accion")
    motivo = (request.POST.get("motivo") or "").strip()
    try:
        if accion == "inhabilitar":
            inhabilitar_estudiante(estudiante_id, request.user, motivo=motivo)
            messages.warning(request, "Estudiante inhabilitado correctamente.")
        elif accion == "habilitar":
            habilitar_estudiante(estudiante_id, request.user)
            messages.success(request, "Estudiante habilitado correctamente.")
        else:
            messages.error(request, "Acción desconocida.")
    except ErrorToggle as exc:
        messages.error(request, f"No se pudo completar la acción: {exc}")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Error inesperado: {exc}")

    return redirect(_url_volver(request))
