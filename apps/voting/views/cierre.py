"""Vistas relacionadas al cierre del proceso y al acta de resultados."""

import os

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.contrib import messages
from django.utils import timezone

from apps.voters.models import ProcesoElectoral
from apps.voting import selectors
from apps.voting.models import ActaCierreProceso
from apps.voting.services.cerrar_proceso import cerrar_proceso

try:
    from xhtml2pdf import pisa
except ImportError:  # pragma: no cover
    pisa = None


# ============================================================
#  Cerrar proceso
# ============================================================
@staff_member_required
def cerrar_proceso_view(request):
    proceso = ProcesoElectoral.objects.filter(activo=True, cerrado=False).first()
    if not proceso:
        return render(request, "voting/cerrar_confirm.html", {"proceso": None})

    if request.method == "POST":
        # Doble validación: exigir la palabra CERRAR en el POST
        confirmacion = (request.POST.get("confirmacion") or "").strip().upper()
        if confirmacion != "CERRAR":
            messages.error(
                request,
                "Debe escribir la palabra CERRAR para confirmar el cierre.",
            )
            return redirect("cerrar_proceso")

        acta = cerrar_proceso(proceso, request.user)
        return redirect("acta_detalle", acta_id=acta.id)

    # Métricas para mostrar en la confirmación
    from apps.voting import selectors  # import local para evitar ciclos

    general = selectors.metricas_general(proceso) if hasattr(selectors, "metricas_general") \
        else selectors.metricas_generales(proceso)
    mesas = selectors.participacion_por_mesa(proceso)

    context = {
        "proceso": proceso,
        "general": general,
        "mesas": mesas,
        "total_tipos": proceso.tipos_eleccion.filter(es_activo=True).count(),
        "total_listas": proceso.listas.filter(es_activo=True).count(),
    }
    return render(request, "voting/cerrar_confirm.html", context)


# ============================================================
#  Detalle del acta (HTML)
# ============================================================
@staff_member_required
def acta_detalle(request, acta_id):
    acta = get_object_or_404(ActaCierreProceso, id=acta_id)
    return render(
        request,
        "voting/acta_detalle.html",
        {"acta": acta, "proceso": acta.proceso},
    )


# ============================================================
#  Generación del PDF
# ============================================================
def _link_callback(uri, rel):
    """Resuelve rutas de imágenes y estáticos para xhtml2pdf.

    xhtml2pdf no descarga URLs remotas ni pasa por el servidor de Django.
    Este callback traduce:
      - rutas absolutas del SO         → tal cual
      - /media/...                    → MEDIA_ROOT/...
      - /static/...                   → STATIC_ROOT o STATICFILES_DIRS[0]/...
    """
    # 1. Ruta absoluta del sistema de archivos
    if os.path.isabs(uri) and os.path.exists(uri):
        return uri

    # 2. Media
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    media_root = getattr(settings, "MEDIA_ROOT", None)
    if media_root and uri.startswith(media_url):
        rel_path = uri[len(media_url):]
        full = os.path.join(str(media_root), rel_path)
        if os.path.exists(full):
            return full

    # 3. Static
    static_url = getattr(settings, "STATIC_URL", "/static/")
    if uri.startswith(static_url):
        rel_path = uri[len(static_url):]
        static_root = getattr(settings, "STATIC_ROOT", None)
        candidates = []
        if static_root:
            candidates.append(os.path.join(str(static_root), rel_path))
        for d in getattr(settings, "STATICFILES_DIRS", []) or []:
            candidates.append(os.path.join(str(d), rel_path))
        for c in candidates:
            if os.path.exists(c):
                return c

    # 4. Fallback: devolver tal cual
    return uri


@staff_member_required
def generar_acta_pdf_view(request, acta_id):
    """Genera el PDF oficial del acta y lo devuelve como descarga."""
    if pisa is None:
        return HttpResponse(
            "Falta la librería xhtml2pdf. Ejecute: pip install xhtml2pdf",
            status=500,
        )

    acta = get_object_or_404(ActaCierreProceso, id=acta_id)

    context = {
        "acta": acta,
        "proceso": acta.proceso,
    }

    template = get_template("voting/acta_pdf_template.html")
    html = template.render(context)

    response = HttpResponse(content_type="application/pdf")
    filename = f"Acta_Cierre_{acta.proceso.id}_{acta.id}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    pisa_status = pisa.CreatePDF(
        html,
        dest=response,
        encoding="utf-8",
        link_callback=_link_callback,
    )

    if pisa_status.err:
        # En caso de error, devolvemos el HTML para inspección
        return HttpResponse(
            f"<h1>Error al generar el PDF</h1><pre>{html}</pre>",
            status=500,
            content_type="text/html",
        )

    return response


# ============================================================
#  Reporte de padrón por mesas (PDF)
# ============================================================
@staff_member_required
def generar_padron_pdf_view(request):
    """Genera el PDF del padrón por mesas (todas, una mesa o sin mesa)."""
    if pisa is None:
        return HttpResponse(
            "Falta la librería xhtml2pdf. Ejecute: pip install xhtml2pdf",
            status=500,
        )

    proceso = ProcesoElectoral.objects.filter(activo=True, cerrado=False).first()
    if not proceso:
        return HttpResponse("No hay un proceso electoral activo.", status=404)

    raw_mesa = (request.GET.get("mesa") or "").strip()
    mesa_id = int(raw_mesa) if raw_mesa.isdigit() else None
    solo_sin_mesa = request.GET.get("estado") == "sin_mesa"

    datos = selectors.padron_por_mesas(
        proceso,
        mesa_id=mesa_id,
        solo_sin_mesa=solo_sin_mesa,
    )

    context = {
        "proceso": proceso,
        "fecha_generado": timezone.now(),
        "variante": datos["estado"],
        "resumen": datos["resumen"],
        "mesas": datos["mesas"],
        "sin_mesa": datos["sin_mesa"],
    }

    template = get_template("voting/padron_mesas_pdf_template.html")
    html = template.render(context)

    response = HttpResponse(content_type="application/pdf")
    sufijo = {"mesa": f"mesa_{mesa_id}", "sin_mesa": "sin_mesa"}.get(
        datos["estado"], "todas"
    )
    filename = f"Padron_Por_Mesas_{proceso.id}_{sufijo}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    pisa_status = pisa.CreatePDF(
        html,
        dest=response,
        encoding="utf-8",
        link_callback=_link_callback,
    )

    if pisa_status.err:
        return HttpResponse(
            f"<h1>Error al generar el PDF</h1><pre>{html}</pre>",
            status=500,
            content_type="text/html",
        )

    return response
